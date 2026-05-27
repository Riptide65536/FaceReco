from __future__ import annotations

import hashlib
import os
import threading
import ctypes
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional
import sys

if TYPE_CHECKING:
    import numpy as np

from paths import MODEL_DIR, asset_path
from services.face_detector import BaseFaceDetector, FaceDetection, InsightFaceDetector, YOLOFaceDetector


class FaceRecognitionService:
    """Face recognition service with deep/LBPH dual backend fallback."""

    _backend_status_lock = threading.Lock()
    _backend_error_message: Optional[str] = None
    _dll_dir_handles: list[object] = []

    def __init__(
        self,
        cascade_path: str = asset_path("haarcascade_frontalface_default.xml"),
        model_path: str = str(Path(MODEL_DIR) / "model.yml"),
        confidence_threshold: float = 68.0,
        labels: Optional[dict[int, str]] = None,
    ) -> None:
        self.cascade_path = Path(cascade_path)
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold
        self.labels = labels or {}
        self._lock = threading.RLock()
        self.cv2 = self._load_cv2()
        self.detector = None
        self.recognizer = None
        self._deep_embedder = None
        self._deep_detector: BaseFaceDetector | None = None
        self._gallery: dict[int, "np.ndarray"] = {}
        self._backend_mode = "deep"
        self._similarity_threshold = (
            float(confidence_threshold) / 100.0
            if float(confidence_threshold) > 1.0
            else float(confidence_threshold)
        )
        self._lbph_threshold = float(confidence_threshold)
        if self._lbph_threshold <= 1.0:
            self._lbph_threshold = 68.0

        self._backend = None
        self._deep_providers: list[str] = []
        self._deep_input_size = (112, 112)
        self._frame_cache_lock = threading.Lock()
        self._frame_cache: dict[str, list[dict[str, Any]]] = {}
        self._frame_cache_order: list[str] = []
        self._frame_cache_limit = max(4, int(os.getenv("FACE_RECO_FRAME_CACHE", "16")))
        self._frame_cache_min_interval = max(0.0, float(os.getenv("FACE_RECO_CACHE_TTL", "0.35")))
        self._frame_cache_max_age = max(self._frame_cache_min_interval, float(os.getenv("FACE_RECO_CACHE_MAX_AGE", "1.2")))
        self._init_backend_with_fallback()
        if self.model_path.exists():
            try:
                self.load_model()
            except Exception:
                pass

    @staticmethod
    def _load_cv2():
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError("OpenCV is not installed. Run: pip install -r requirements.txt") from exc
        return cv2

    def backend_mode(self) -> str:
        return self._backend_mode

    def set_realtime_mode(self, mode: str) -> None:
        mode = str(mode or "").strip().lower()
        presets = {
            "realtime": (0.18, 0.60),
            "balanced": (0.35, 1.20),
            "accurate": (0.60, 2.00),
        }
        cache_ttl, cache_age = presets.get(mode, presets["balanced"])
        self._frame_cache_min_interval = max(0.0, float(cache_ttl))
        self._frame_cache_max_age = max(self._frame_cache_min_interval, float(cache_age))
        if self._deep_detector is not None and hasattr(self._deep_detector, "set_runtime_mode"):
            try:
                self._deep_detector.set_runtime_mode(mode)
            except Exception:
                pass

    def _init_backend_with_fallback(self) -> None:
        try:
            self._backend = self._create_deep_backend()
            self._backend_mode = "deep"
            return
        except Exception:
            pass
        try:
            self._backend = self._create_lbph_backend()
            self._backend_mode = "lbph"
            return
        except Exception:
            pass
        self._backend = self._create_lite_backend()
        self._backend_mode = "lite"

    def _create_deep_backend(self):
        with self._backend_status_lock:
            if self._backend_error_message:
                raise RuntimeError(self._backend_error_message)

        # Import torch before ORT/InsightFace on Windows so PyTorch resolves its
        # CUDA/cuDNN DLL chain first. This avoids later YOLO initialization
        # falling back when ORT has already altered the DLL search order.
        self._prime_torch_runtime()

        try:
            from insightface.app import FaceAnalysis  # type: ignore
        except Exception as exc:
            message = (
                "Deep face backend is unavailable. Install: insightface + onnxruntime. "
                "See README for setup."
            )
            with self._backend_status_lock:
                self._backend_error_message = message
            raise RuntimeError(message) from exc

        providers = self._resolve_ort_providers()
        self._deep_providers = list(providers)
        print("face backend providers:", providers)
        det_size = (320, 320) if os.getenv("FACE_RECO_DEEP_DET_SIZE", "").strip() == "" else None
        if det_size is None:
            try:
                size_raw = os.getenv("FACE_RECO_DEEP_DET_SIZE", "320").strip()
                size_v = int(size_raw)
                size_v = max(160, min(640, size_v))
                det_size = (size_v, size_v)
            except Exception:
                det_size = (320, 320)
        try:
            analyzer = FaceAnalysis(name="buffalo_l", providers=providers)
            analyzer.prepare(ctx_id=-1, det_size=det_size)
            recognition_model = getattr(analyzer, "models", {}).get("recognition")
            if recognition_model is None:
                raise RuntimeError("InsightFace recognition model is unavailable in buffalo_l.")
            self._deep_embedder = recognition_model
            self.recognizer = recognition_model
            self._deep_input_size = tuple(getattr(recognition_model, "input_size", (112, 112)))
            self._deep_detector = self._create_deep_detector(
                providers=providers,
                det_size=det_size,
                analyzer=analyzer,
            )
            self.detector = self._deep_detector
            detector_name = type(self._deep_detector).__name__
            if isinstance(self._deep_detector, YOLOFaceDetector):
                print(
                    "face detector:",
                    f"{detector_name} ({self._deep_detector.model_path})",
                    f"device={getattr(self._deep_detector, 'device', None)}",
                    f"imgsz={getattr(self._deep_detector, 'imgsz', None)}",
                )
            else:
                print(f"face detector: {detector_name}")
            return {
                "analyzer": analyzer,
                "embedder": recognition_model,
                "detector": self._deep_detector,
            }
        except Exception as exc:
            model_dir = Path.home() / ".insightface" / "models" / "buffalo_l"
            message = (
                "Deep face backend initialization failed. "
                f"If your network cannot access GitHub, manually place 'buffalo_l' into: {model_dir}"
            )
            with self._backend_status_lock:
                self._backend_error_message = message
            raise RuntimeError(message) from exc

    def _create_deep_detector(
        self,
        providers: list[str],
        det_size: tuple[int, int],
        analyzer: Any | None = None,
    ) -> BaseFaceDetector:
        yolo_model_path = self._resolve_yolo_model_path()
        yolo_conf = float(os.getenv("FACE_RECO_YOLO_CONF", "0.25"))
        yolo_iou = float(os.getenv("FACE_RECO_YOLO_IOU", "0.45"))
        yolo_imgsz = int(os.getenv("FACE_RECO_YOLO_IMGSZ", "640"))
        yolo_device = self._resolve_yolo_device()

        try:
            return YOLOFaceDetector(
                model_path=yolo_model_path,
                conf_threshold=yolo_conf,
                iou_threshold=yolo_iou,
                imgsz=yolo_imgsz,
                device=yolo_device,
            )
        except Exception:
            return InsightFaceDetector(providers=providers, det_size=det_size, analyzer=analyzer)

    @staticmethod
    def _resolve_yolo_model_path() -> Path:
        env_path = os.getenv("FACE_RECO_YOLO_MODEL", "").strip()
        candidates: list[Path] = []
        if env_path:
            candidates.append(Path(env_path).expanduser())

        repo_root = Path(MODEL_DIR).parent
        candidates.extend(
            [
                Path(MODEL_DIR) / "yolov8n-face.pt",
                repo_root / "models" / "yolov8n-face.pt",
                Path(MODEL_DIR) / "yolov10n-face.pt",
                repo_root / "models" / "yolov10n-face.pt",
            ]
        )

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    @staticmethod
    def _prime_torch_runtime() -> None:
        try:
            import torch  # type: ignore

            _ = torch.cuda.is_available()
        except Exception:
            pass

    @staticmethod
    def _resolve_yolo_device() -> str | None:
        env_device = os.getenv("FACE_RECO_YOLO_DEVICE", "").strip()
        if env_device:
            return env_device
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                return "0"
            return "cpu"
        except Exception:
            return None

    @staticmethod
    def _resolve_ort_providers() -> list[str]:
        FaceRecognitionService._setup_windows_dll_dirs()
        verbose = os.getenv("FACE_RECO_VERBOSE", "0") == "1"
        preferred = os.getenv("FACE_RECO_ORT_PROVIDER", "").strip()
        available: list[str] = []
        try:
            import onnxruntime as ort  # type: ignore
            try:
                # Best effort preload for CUDA/cuDNN/MSVC runtime DLLs.
                if hasattr(ort, "preload_dlls"):
                    ort.preload_dlls()  # type: ignore[attr-defined]
            except Exception:
                pass

            available = list(ort.get_available_providers())
        except Exception:
            available = []
        if verbose:
            print("ort available providers:", available)

        enable_trt = os.getenv("FACE_RECO_ENABLE_TRT", "0") == "1"
        order = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if enable_trt:
            order.insert(1, "TensorrtExecutionProvider")
        selected = [p for p in order if p in available]

        if preferred:
            pref_norm = preferred
            if not pref_norm.endswith("ExecutionProvider"):
                pref_norm = f"{pref_norm}ExecutionProvider"
            if pref_norm in selected:
                selected = [pref_norm] + [p for p in selected if p != pref_norm]

        if not selected:
            selected = ["CPUExecutionProvider"]
        elif "CPUExecutionProvider" not in selected:
            selected.append("CPUExecutionProvider")

        # Validate the provider list by creating a tiny throwaway session.
        # This catches Windows initialization failures early and lets us fall
        # back to CPU without spamming every subsequent model load.
        if "CUDAExecutionProvider" in selected and os.name == "nt":
            if not FaceRecognitionService._probe_cuda_session():
                if verbose:
                    print("cuda provider probe failed, falling back to CPU")
                selected = ["CPUExecutionProvider"]
        return selected

    @staticmethod
    def _probe_cuda_session() -> bool:
        try:
            import onnxruntime as ort  # type: ignore
            import tempfile
            import numpy as np

            model = FaceRecognitionService._build_tiny_onnx_identity_model()
            with tempfile.TemporaryDirectory() as td:
                model_path = Path(td) / "probe.onnx"
                model_path.write_bytes(model)
                sess = ort.InferenceSession(
                    str(model_path),
                    providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
                )
                x = np.zeros((1, 1), dtype=np.float32)
                sess.run(None, {"x": x})
            return True
        except Exception as exc:
            if os.getenv("FACE_RECO_VERBOSE", "0") == "1":
                print(f"cuda session probe failed: {type(exc).__name__}: {exc}")
            return False

    @staticmethod
    def _build_tiny_onnx_identity_model() -> bytes:
        # Minimal ONNX identity graph. Serialized manually to avoid adding a
        # hard dependency on onnx for the probe path.
        import struct

        def varint(n: int) -> bytes:
            out = bytearray()
            while True:
                b = n & 0x7F
                n >>= 7
                if n:
                    out.append(b | 0x80)
                else:
                    out.append(b)
                    break
            return bytes(out)

        def field(tag: int, data: bytes) -> bytes:
            return varint(tag) + varint(len(data)) + data

        def str_field(tag: int, text: str) -> bytes:
            raw = text.encode("utf-8")
            return field(tag, raw)

        def tensor_value_info(name: str) -> bytes:
            # ValueInfoProto: name + type(float tensor, [1,1])
            dims = field(1, varint(1)) + field(1, varint(1))
            tensor_shape = field(2, dims)
            tensor_type = field(1, varint(1)) + field(2, tensor_shape)
            type_proto = field(1, tensor_type)
            return str_field(1, name) + field(2, type_proto)

        # This handcrafted payload is intentionally tiny and only used for a
        # CUDA provider smoke test.
        # A more complete ONNX builder would be overkill here.
        try:
            import onnx  # type: ignore
            from onnx import TensorProto, helper  # type: ignore

            x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1])
            y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1])
            node = helper.make_node("Identity", ["x"], ["y"])
            graph = helper.make_graph([node], "probe", [x], [y])
            model = helper.make_model(graph, producer_name="face-reco-probe")
            return model.SerializeToString()
        except Exception:
            # If onnx is unavailable, return an empty payload and let the probe
            # fail fast rather than blocking startup.
            return b""

    @staticmethod
    def _setup_windows_dll_dirs() -> None:
        if os.name != "nt":
            return
        if not hasattr(os, "add_dll_directory"):
            return
        if FaceRecognitionService._dll_dir_handles:
            return

        candidate_dirs: list[Path] = []
        # Collect nvidia runtime bins installed by pip packages.
        for sp in [Path(p) for p in sys.path if "site-packages" in p]:
            nvidia_root = sp / "nvidia"
            if not nvidia_root.exists():
                continue
            # Do not hardcode package names; different ORT/CUDA builds can
            # depend on additional nvidia wheels (cufft/curand/cusparse/...).
            for sub in nvidia_root.iterdir():
                if not sub.is_dir():
                    continue
                bin_dir = sub / "bin"
                if bin_dir.exists():
                    candidate_dirs.append(bin_dir)
            # onnxruntime capi directory may also be needed in DLL search path.
            ort_capi = sp / "onnxruntime" / "capi"
            if ort_capi.exists():
                candidate_dirs.append(ort_capi)

        # Deduplicate while preserving order.
        seen = set()
        unique_dirs: list[Path] = []
        for d in candidate_dirs:
            key = str(d).lower()
            if key in seen:
                continue
            seen.add(key)
            unique_dirs.append(d)

        if not unique_dirs:
            return

        verbose = os.getenv("FACE_RECO_VERBOSE", "0") == "1"
        if verbose:
            print("ort dll dirs count:", len(unique_dirs))
            for d in unique_dirs:
                print("ort dll dir:", d)

        # Keep handles alive for the process lifetime.
        for d in unique_dirs:
            try:
                handle = os.add_dll_directory(str(d))
                FaceRecognitionService._dll_dir_handles.append(handle)
            except Exception:
                pass

        # Keep PATH aligned for third-party loaders.
        current_path = os.environ.get("PATH", "")
        prepend = ";".join(str(d) for d in unique_dirs)
        os.environ["PATH"] = f"{prepend};{current_path}" if current_path else prepend

    @staticmethod
    def _provider_dll_ready(provider_name: str) -> bool:
        if provider_name == "CPUExecutionProvider":
            return True
        dll_map = {
            "CUDAExecutionProvider": "onnxruntime_providers_cuda.dll",
            "TensorrtExecutionProvider": "onnxruntime_providers_tensorrt.dll",
        }
        dll_name = dll_map.get(provider_name)
        if not dll_name:
            return True
        try:
            import onnxruntime as ort  # type: ignore

            capi_dir = Path(ort.__file__).resolve().parent / "capi"
            dll_path = capi_dir / dll_name
            if not dll_path.exists():
                return False
            ctypes.WinDLL(str(dll_path))
            return True
        except Exception as exc:
            if os.getenv("FACE_RECO_VERBOSE", "0") == "1":
                print(f"ort provider dll probe failed: {provider_name} -> {exc}")
            return False

    def _create_lbph_backend(self):
        try:
            if not self.cascade_path.exists():
                raise RuntimeError(f"Haar cascade file is missing: {self.cascade_path}")
            detector = self.cv2.CascadeClassifier(str(self.cascade_path))
            if detector.empty():
                raise RuntimeError(f"Failed to load Haar cascade: {self.cascade_path}")
            if not hasattr(self.cv2, "face") or (not hasattr(self.cv2.face, "LBPHFaceRecognizer_create")):
                raise RuntimeError("LBPH backend is unavailable. Install opencv-contrib-python.")
            recognizer = self.cv2.face.LBPHFaceRecognizer_create()
            self.detector = detector
            self.recognizer = recognizer
            return recognizer
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("LBPH backend is unavailable. Install opencv-contrib-python.") from exc

    def _create_lite_backend(self):
        # Lightweight fallback backend (no cv2.face / no deep model) that still
        # supports training and recognition with simple normalized pixel features.
        self.recognizer = None
        if self.cascade_path.exists():
            try:
                detector = self.cv2.CascadeClassifier(str(self.cascade_path))
                self.detector = None if detector.empty() else detector
            except Exception:
                self.detector = None
        else:
            self.detector = None
        return object()

    @staticmethod
    def _normalize(vec: "np.ndarray") -> "np.ndarray":
        import numpy as np

        v = np.asarray(vec, dtype="float32").reshape(-1)
        n = float(np.linalg.norm(v))
        if n <= 1e-12:
            return v
        return v / n

    def _ensure_bgr(self, frame: "np.ndarray") -> "np.ndarray":
        if len(frame.shape) == 2:
            return self.cv2.cvtColor(frame, self.cv2.COLOR_GRAY2BGR)
        return frame

    @staticmethod
    def _frame_cache_key(frame: "np.ndarray") -> str:
        try:
            import numpy as np

            contiguous = np.ascontiguousarray(frame)
            digest = hashlib.blake2b(contiguous.view("uint8"), digest_size=16).hexdigest()
            return f"{contiguous.shape}:{contiguous.dtype}:{digest}"
        except Exception:
            return ""

    def _cached_predictions(self, frame: "np.ndarray") -> list[dict[str, Any]] | None:
        if self._frame_cache_min_interval <= 0:
            return None
        cache_key = self._frame_cache_key(frame)
        if not cache_key:
            return None
        import time

        now = time.monotonic()
        with self._frame_cache_lock:
            cached = self._frame_cache.get(cache_key)
            if cached is None:
                return None
            age = now - float(cached[0])  # type: ignore[index]
            if age > self._frame_cache_max_age:
                self._frame_cache.pop(cache_key, None)
                if cache_key in self._frame_cache_order:
                    self._frame_cache_order.remove(cache_key)
                return None
            return list(cached[1])  # type: ignore[index]

    def _store_cached_predictions(self, frame: "np.ndarray", predictions: list[dict[str, Any]]) -> None:
        cache_key = self._frame_cache_key(frame)
        if not cache_key:
            return
        import time

        payload = (time.monotonic(), [dict(item) for item in predictions])
        with self._frame_cache_lock:
            self._frame_cache[cache_key] = payload
            if cache_key in self._frame_cache_order:
                self._frame_cache_order.remove(cache_key)
            self._frame_cache_order.append(cache_key)
            while len(self._frame_cache_order) > self._frame_cache_limit:
                old = self._frame_cache_order.pop(0)
                self._frame_cache.pop(old, None)

    def _extract_faces_deep(self, frame: "np.ndarray") -> list[dict[str, Any]]:
        bgr = self._ensure_bgr(frame)
        detections = self._detect_faces_deep(bgr)
        results: list[dict[str, Any]] = []
        for det in detections:
            embedding = self._extract_embedding_from_detection(bgr, det)
            if embedding is None:
                continue
            results.append({"bbox": tuple(map(int, det.bbox)), "embedding": embedding})
        return results

    def _detect_faces_deep(self, frame: "np.ndarray") -> list[FaceDetection]:
        bgr = self._ensure_bgr(frame)
        if self._deep_detector is None:
            return []
        return self._deep_detector.detect(bgr)

    def _extract_embedding_from_detection(
        self,
        frame_bgr: "np.ndarray",
        detection: FaceDetection,
    ) -> Optional["np.ndarray"]:
        if self._deep_embedder is None:
            return None

        x, y, w, h = [int(v) for v in detection.bbox]
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(frame_bgr.shape[1], x0 + max(1, w))
        y1 = min(frame_bgr.shape[0], y0 + max(1, h))
        if x1 <= x0 or y1 <= y0:
            return None

        if detection.kps is not None:
            embedding = self._extract_embedding_with_kps(frame_bgr, detection.kps)
            if embedding is not None:
                return embedding

        embedding = self._extract_embedding_via_recognition_detector(frame_bgr, detection.bbox)
        if embedding is not None:
            return embedding

        face_crop = frame_bgr[y0:y1, x0:x1]
        if face_crop.size == 0:
            return None

        embedding = self._extract_embedding_from_crop(face_crop)
        if embedding is not None:
            return embedding

        return None

    @staticmethod
    def _normalize_five_point_kps(kps: "np.ndarray") -> Optional["np.ndarray"]:
        import numpy as np

        parsed = np.asarray(kps, dtype="float32")
        if parsed.ndim != 2 or parsed.shape[1] < 2 or parsed.shape[0] < 5:
            return None
        if parsed.shape[0] != 5:
            return None
        return parsed[:, :2]

    def _extract_embedding_with_kps(
        self,
        frame_bgr: "np.ndarray",
        kps: "np.ndarray",
    ) -> Optional["np.ndarray"]:
        normalized_kps = self._normalize_five_point_kps(kps)
        if normalized_kps is not None:
            try:
                from insightface.utils import face_align  # type: ignore
            except Exception:
                return None

            try:
                aligned = face_align.norm_crop(frame_bgr, landmark=normalized_kps)
            except Exception:
                aligned = None
            if aligned is not None:
                return self._extract_embedding_with_embedder(aligned)

        try:
            from insightface.app.common import Face  # type: ignore
        except Exception:
            return None

        try:
            face = Face(kps=kps)
            embedding = self._deep_embedder.get(frame_bgr, face)
        except Exception:
            return None
        if embedding is None:
            embedding = getattr(face, "embedding", None)
        if embedding is None:
            return None
        return self._normalize(embedding)

    def _prepare_arcface_crop(self, face_crop: "np.ndarray") -> Optional["np.ndarray"]:
        prepared = self._ensure_bgr(face_crop)
        if prepared.size == 0:
            return None
        target_w, target_h = self._deep_input_size
        if target_w <= 0 or target_h <= 0:
            target_w, target_h = 112, 112
        if prepared.shape[1] != target_w or prepared.shape[0] != target_h:
            prepared = self.cv2.resize(prepared, (int(target_w), int(target_h)))
        return prepared

    def _extract_embedding_from_crop(self, face_crop: "np.ndarray") -> Optional["np.ndarray"]:
        prepared_crop = self._prepare_arcface_crop(face_crop)
        candidates = [prepared_crop] if prepared_crop is not None else []
        try:
            gray = self.to_gray(face_crop)
            if gray.size > 0:
                tight = self.cv2.resize(gray, tuple(map(int, self._deep_input_size)))
                candidates.insert(0, self.cv2.cvtColor(tight, self.cv2.COLOR_GRAY2BGR))
        except Exception:
            pass

        for candidate in candidates:
            if candidate is None:
                continue
            emb = self._extract_embedding_with_embedder(candidate)
            if emb is not None:
                return emb
        return None

    def _extract_embedding_with_embedder(self, face_crop: "np.ndarray") -> Optional["np.ndarray"]:
        if self._deep_embedder is None:
            return None
        try:
            embedding = self._deep_embedder.get_feat(face_crop)
        except Exception:
            return None
        if embedding is None:
            return None
        return self._normalize(embedding)

    def _extract_embedding_via_recognition_detector(
        self,
        frame_bgr: "np.ndarray",
        bbox: tuple[int, int, int, int],
    ) -> Optional["np.ndarray"]:
        if self._deep_embedder is None:
            return None

        x, y, w, h = [int(v) for v in bbox]
        pad = max(8, int(0.2 * max(w, h)))
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(frame_bgr.shape[1], x + w + pad)
        y1 = min(frame_bgr.shape[0], y + h + pad)
        if x1 <= x0 or y1 <= y0:
            return None
        analyzer = self._backend.get("analyzer") if isinstance(self._backend, dict) else None
        if analyzer is None:
            return None
        try:
            faces = analyzer.get(frame_bgr[y0:y1, x0:x1])
        except Exception:
            return None
        if not faces:
            return None
        selected = max(
            faces,
            key=lambda item: float(getattr(item, "det_score", 0.0)) * float(
                max(1.0, (getattr(item, "bbox", [0, 0, 0, 0])[2] - getattr(item, "bbox", [0, 0, 0, 0])[0]))
                * max(1.0, (getattr(item, "bbox", [0, 0, 0, 0])[3] - getattr(item, "bbox", [0, 0, 0, 0])[1]))
            ),
        )
        embedding = getattr(selected, "normed_embedding", None)
        if embedding is None:
            embedding = getattr(selected, "embedding", None)
        if embedding is None:
            return None
        return self._normalize(embedding)

    def _extract_single_embedding(self, sample: "np.ndarray", assume_face_crop: bool = False) -> Optional["np.ndarray"]:
        if assume_face_crop:
            try:
                gray_face = self.to_gray(sample)
                if gray_face.size > 0:
                    fast_face = self.cv2.resize(gray_face, (112, 112))
                    fast_bgr = self.cv2.cvtColor(fast_face, self.cv2.COLOR_GRAY2BGR)
                    embedding = self._extract_embedding_from_crop(fast_bgr)
                    if embedding is not None:
                        return embedding
            except Exception:
                pass

        # Try original sample first.
        candidates = [sample]
        # Upscale tiny crops to improve deep detector success on pre-cropped faces.
        try:
            gray = self.to_gray(sample)
            h, w = gray.shape[:2]
            min_side = min(h, w)
            if min_side < 160:
                scale = max(2.0, 192.0 / float(max(1, min_side)))
                up = self.cv2.resize(sample, None, fx=scale, fy=scale)
                candidates.append(up)
            # Add padded version to recover context for very tight crops.
            pad = max(10, int(0.15 * max(h, w)))
            padded = self.cv2.copyMakeBorder(sample, pad, pad, pad, pad, self.cv2.BORDER_REFLECT_101)
            candidates.append(padded)
        except Exception:
            pass

        for candidate in candidates:
            detections = self._detect_faces_deep(candidate)
            if not detections:
                continue
            selected = max(detections, key=lambda item: int(item.bbox[2]) * int(item.bbox[3]))
            embedding = self._extract_embedding_from_detection(self._ensure_bgr(candidate), selected)
            if embedding is not None:
                return embedding
        return None

    def _compute_lite_embedding(self, frame: "np.ndarray", bbox: tuple[int, int, int, int] | None = None):
        gray = self.to_gray(frame)
        if bbox is not None:
            x, y, w, h = bbox
            face = gray[max(0, y) : max(0, y) + max(1, h), max(0, x) : max(0, x) + max(1, w)]
        else:
            face = gray
        if face.size == 0:
            return None
        resized = self.cv2.resize(face, (64, 64))
        normed = resized.astype("float32") / 255.0
        return self._normalize(normed.reshape(-1))

    def _extract_faces_lite(self, frame: "np.ndarray") -> list[dict[str, Any]]:
        boxes = self._detect_faces_lbph(frame)
        if not boxes:
            h, w = self.to_gray(frame).shape[:2]
            boxes = [(0, 0, int(w), int(h))]
        results: list[dict[str, Any]] = []
        for box in boxes:
            emb = self._compute_lite_embedding(frame, box)
            if emb is None:
                continue
            results.append({"bbox": tuple(map(int, box)), "embedding": emb})
        return results

    def _detect_faces_lbph(self, frame: "np.ndarray") -> list[tuple[int, int, int, int]]:
        if self.detector is None:
            return []
        gray = self.to_gray(frame)
        faces = self.detector.detectMultiScale(gray, 1.3, 5)
        return [tuple(map(int, f)) for f in faces]

    def load_model(self) -> bool:
        import numpy as np

        with self._lock:
            if self._backend_mode in {"deep", "lite"}:
                with open(self.model_path, "rb") as fd:
                    payload = np.load(fd, allow_pickle=False)
                    labels = payload["labels"].astype("int32").tolist()
                    embeddings = payload["embeddings"].astype("float32")
                self._gallery = {
                    int(label): self._normalize(embeddings[idx]) for idx, label in enumerate(labels)
                }
                return True

            if self.recognizer is None:
                return False
            self.recognizer.read(str(self.model_path))
            return True

    def detect_faces(self, frame: "np.ndarray") -> list[tuple[int, int, int, int]]:
        with self._lock:
            if self._backend_mode == "deep":
                return [tuple(map(int, det.bbox)) for det in self._detect_faces_deep(frame)]
            if self._backend_mode == "lite":
                return [tuple(map(int, f["bbox"])) for f in self._extract_faces_lite(frame)]
            return self._detect_faces_lbph(frame)

    def recognize_frame(self, frame: "np.ndarray") -> list[dict[str, Any]]:
        results = []
        with self._lock:
            cached = self._cached_predictions(frame)
            if cached is not None:
                return cached
            if self._backend_mode in {"deep", "lite"}:
                faces = self._extract_faces_deep(frame) if self._backend_mode == "deep" else self._extract_faces_lite(frame)
                for det in faces:
                    x, y, w, h = det["bbox"]
                    name = "unknown"
                    confidence = None
                    label = None
                    similarity = None
                    emb = self._normalize(det["embedding"])
                    if self._gallery:
                        best_label = None
                        best_sim = -1.0
                        for gid, gemb in self._gallery.items():
                            sim = float((emb * gemb).sum())
                            if sim > best_sim:
                                best_sim = sim
                                best_label = int(gid)
                        if best_label is not None:
                            label = best_label
                            similarity = best_sim
                            confidence = max(0.0, min(100.0, best_sim * 100.0))
                            if best_sim >= self._similarity_threshold:
                                name = self.labels.get(int(best_label), str(best_label))
                    results.append(
                        {
                            "bbox": (x, y, w, h),
                            "label": label,
                            "name": name,
                            "similarity": similarity,
                            "confidence": confidence,
                        }
                    )
                self._store_cached_predictions(frame, results)
                return results

            if self.recognizer is None:
                return results
            gray = self.to_gray(frame)
            faces = self._detect_faces_lbph(gray)
            for (x, y, w, h) in faces:
                face = gray[y : y + h, x : x + w]
                label_id, dist = self.recognizer.predict(face)
                label = int(label_id)
                name = "unknown"
                if float(dist) < self._lbph_threshold:
                    name = self.labels.get(label, "unknown")
                confidence = max(0.0, min(100.0, 100.0 - float(dist)))
                results.append(
                    {
                        "bbox": (x, y, w, h),
                        "label": label,
                        "name": name,
                        "similarity": max(0.0, min(1.0, confidence / 100.0)),
                        "confidence": confidence,
                    }
                )
            self._store_cached_predictions(frame, results)
        return results

    def train(self, samples: Iterable["np.ndarray"], labels: Iterable[int]) -> None:
        import numpy as np

        samples = list(samples)
        labels_array = np.array(list(labels), dtype="int32")
        if not samples or len(samples) != len(labels_array):
            raise ValueError("Face samples and labels must be non-empty and have the same length.")

        with self._lock:
            if self._backend_mode in {"deep", "lite"}:
                per_label: dict[int, list["np.ndarray"]] = {}
                # If a class has multiple samples, treat them as enrollment crops
                # and use a faster extraction path first.
                label_counts: dict[int, int] = {}
                for label in labels_array.tolist():
                    ilabel = int(label)
                    label_counts[ilabel] = label_counts.get(ilabel, 0) + 1
                for sample, label in zip(samples, labels_array):
                    ilabel = int(label)
                    assume_face_crop = label_counts.get(ilabel, 0) > 1
                    emb = (
                        self._extract_single_embedding(sample, assume_face_crop=assume_face_crop)
                        if self._backend_mode == "deep"
                        else self._compute_lite_embedding(sample, None)
                    )
                    if emb is None:
                        continue
                    per_label.setdefault(ilabel, []).append(emb)

                if not per_label:
                    raise ValueError("No valid face embeddings were extracted from samples.")

                gallery_labels = sorted(per_label.keys())
                gallery_embeddings = []
                for label in gallery_labels:
                    stack = np.stack(per_label[label], axis=0)
                    centroid = self._normalize(np.mean(stack, axis=0))
                    gallery_embeddings.append(centroid)

                embeddings_np = np.stack(gallery_embeddings, axis=0).astype("float32")
                labels_np = np.array(gallery_labels, dtype="int32")

                self.model_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.model_path, "wb") as fd:
                    np.savez_compressed(fd, labels=labels_np, embeddings=embeddings_np)

                self._gallery = {
                    int(label): embeddings_np[idx] for idx, label in enumerate(labels_np.tolist())
                }
                return

            if self.recognizer is None:
                raise RuntimeError("LBPH recognizer is not initialized.")
            prepared_samples = [self.to_gray(sample) for sample in samples]
            self.recognizer.train(prepared_samples, labels_array)
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            self.recognizer.save(str(self.model_path))

    def to_gray(self, frame: "np.ndarray") -> "np.ndarray":
        if frame is None:
            raise ValueError("empty frame: None")
        if getattr(frame, "size", 0) == 0:
            raise ValueError("empty frame: zero-sized array")
        if len(frame.shape) == 2:
            return frame
        return self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2GRAY)
