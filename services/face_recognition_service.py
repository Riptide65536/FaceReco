from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional

if TYPE_CHECKING:
    import numpy as np

from paths import MODEL_DIR, asset_path


class FaceRecognitionService:
    """Face recognition service with deep/LBPH dual backend fallback."""

    _backend_status_lock = threading.Lock()
    _backend_error_message: Optional[str] = None

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

        providers = ["CPUExecutionProvider"]
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
            return analyzer
        except Exception as exc:
            model_dir = Path.home() / ".insightface" / "models" / "buffalo_l"
            message = (
                "Deep face backend initialization failed. "
                f"If your network cannot access GitHub, manually place 'buffalo_l' into: {model_dir}"
            )
            with self._backend_status_lock:
                self._backend_error_message = message
            raise RuntimeError(message) from exc

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

    def _extract_faces_deep(self, frame: "np.ndarray") -> list[dict[str, Any]]:
        bgr = self._ensure_bgr(frame)
        faces = self._backend.get(bgr)
        results: list[dict[str, Any]] = []
        for face in faces:
            bbox_raw = getattr(face, "bbox", None)
            if bbox_raw is None:
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox_raw[:4]]
            w = max(0, x2 - x1)
            h = max(0, y2 - y1)
            if w == 0 or h == 0:
                continue
            embedding = getattr(face, "normed_embedding", None)
            if embedding is None:
                embedding = self._normalize(getattr(face, "embedding"))
            else:
                embedding = self._normalize(embedding)
            results.append({"bbox": (x1, y1, w, h), "embedding": embedding})
        return results

    def _extract_single_embedding(self, sample: "np.ndarray") -> Optional["np.ndarray"]:
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
            faces = self._extract_faces_deep(candidate)
            if not faces:
                continue
            selected = max(faces, key=lambda item: int(item["bbox"][2]) * int(item["bbox"][3]))
            return self._normalize(selected["embedding"])
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
                return [tuple(map(int, f["bbox"])) for f in self._extract_faces_deep(frame)]
            if self._backend_mode == "lite":
                return [tuple(map(int, f["bbox"])) for f in self._extract_faces_lite(frame)]
            return self._detect_faces_lbph(frame)

    def recognize_frame(self, frame: "np.ndarray") -> list[dict[str, Any]]:
        results = []
        with self._lock:
            if self._backend_mode in {"deep", "lite"}:
                faces = self._extract_faces_deep(frame) if self._backend_mode == "deep" else self._extract_faces_lite(frame)
                for det in faces:
                    x, y, w, h = det["bbox"]
                    name = "unknown"
                    confidence = None
                    label = None
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
                            confidence = max(0.0, min(100.0, best_sim * 100.0))
                            if best_sim >= self._similarity_threshold:
                                name = self.labels.get(int(best_label), str(best_label))
                    results.append(
                        {
                            "bbox": (x, y, w, h),
                            "label": label,
                            "name": name,
                            "confidence": confidence,
                        }
                    )
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
                        "confidence": confidence,
                    }
                )
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
                for sample, label in zip(samples, labels_array):
                    emb = (
                        self._extract_single_embedding(sample)
                        if self._backend_mode == "deep"
                        else self._compute_lite_embedding(sample, None)
                    )
                    if emb is None:
                        continue
                    per_label.setdefault(int(label), []).append(emb)

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
