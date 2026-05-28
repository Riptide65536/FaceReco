from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import sqls
from app.repositories import DataRepository
from app.state import AppState
from paths import MODEL_DIR, asset_path
from services.emotion_service import EmotionRecognitionService
from services.face_recognition_service import FaceRecognitionService


@dataclass
class RecognitionEvent:
    name: str
    emotion: str
    location: str
    timestamp: datetime.datetime


class RecognitionPipeline:
    """Pure recognition pipeline independent from UI widgets."""

    def __init__(self, state: AppState, confidence_threshold: float = 68.0) -> None:
        self.state = state
        self.confidence_threshold = confidence_threshold
        self.cv2 = self._try_import_cv2()
        self._fallback_detector = self._create_fallback_detector()
        self._face_service_error = ""
        self._last_train_error = ""
        self.face_service = self._create_face_service()
        self.emotion = None
        try:
            self.emotion = EmotionRecognitionService()
        except Exception:
            self.emotion = None
        self._refresh_service_labels()

    @staticmethod
    def _try_import_cv2():
        try:
            import cv2  # type: ignore

            return cv2
        except Exception:
            return None

    def _create_fallback_detector(self):
        if self.cv2 is None:
            return None
        try:
            cascade = self.cv2.CascadeClassifier(asset_path("haarcascade_frontalface_default.xml"))
            if cascade.empty():
                return None
            return cascade
        except Exception:
            return None

    def _create_face_service(self):
        try:
            service = FaceRecognitionService(
                model_path=str(Path(MODEL_DIR) / "model.yml"),
                confidence_threshold=self.confidence_threshold,
                labels=dict(self.state.user_dic),
            )
            self._face_service_error = ""
            return service
        except Exception as exc:
            self._face_service_error = str(exc)
            return None

    def _refresh_service_labels(self) -> None:
        if self.face_service is not None:
            self.face_service.labels = dict(self.state.user_dic)

    def ensure_face_service_ready(self) -> bool:
        if self.face_service is None:
            self.face_service = self._create_face_service()
        self._refresh_service_labels()
        return self.face_service is not None

    def current_backend_mode(self) -> str:
        if self.face_service is None:
            return "unavailable"
        try:
            return str(self.face_service.backend_mode())
        except Exception:
            return "unknown"

    def current_provider_text(self) -> str:
        if self.face_service is None:
            return "unavailable"
        try:
            providers = getattr(self.face_service, "_deep_providers", None)
            if not providers:
                return "unknown"
            return " > ".join(list(providers))
        except Exception:
            return "unknown"

    @staticmethod
    def _provider_alias(provider_name: str) -> str:
        mapping = {
            "CUDAExecutionProvider": "CUDA",
            "CPUExecutionProvider": "CPU",
            "TensorrtExecutionProvider": "TensorRT",
        }
        return mapping.get(str(provider_name), str(provider_name).replace("ExecutionProvider", "") or "unknown")

    def current_provider_display_text(self) -> str:
        backend_mode = self.current_backend_mode()
        if backend_mode == "lbph":
            return "ArcFace：未启用（LBPH 降级）"
        if backend_mode == "lite":
            return "ArcFace：未启用（Lite 应急）"
        if backend_mode == "unavailable":
            return "ArcFace：不可用"
        if backend_mode != "deep":
            return "ArcFace：未知"

        if self.face_service is None:
            return "ArcFace：不可用"
        try:
            providers = list(getattr(self.face_service, "_deep_providers", None) or [])
        except Exception:
            providers = []
        if not providers:
            return "ArcFace：未知"

        primary = self._provider_alias(providers[0])
        fallback = [self._provider_alias(item) for item in providers[1:]]
        if fallback:
            return f"ArcFace：{primary}（回退 {' / '.join(fallback)}）"
        return f"ArcFace：{primary}"

    def current_provider_tooltip(self) -> str:
        backend_mode = self.current_backend_mode()
        provider_text = self.current_provider_text()
        display_text = self.current_provider_display_text()
        if backend_mode == "deep":
            return (
                f"{display_text}\n"
                f"ONNX Runtime Providers：{provider_text}\n"
                "这表示 ArcFace / InsightFace 的识别链优先使用前面的 Provider，失败时再回退。"
            )
        if backend_mode == "lbph":
            return (
                "当前识别后端为 LBPH 降级模式，ArcFace / InsightFace 深度识别链当前未启用。"
            )
        if backend_mode == "lite":
            return (
                "当前识别后端为 Lite 应急模式，ArcFace / InsightFace 深度识别链当前未启用。"
            )
        return f"{display_text}\nONNX Runtime Providers：{provider_text}"

    def face_service_error_text(self) -> str:
        return self._face_service_error.strip()

    def last_train_error_text(self) -> str:
        return self._last_train_error.strip()

    def _detect_faces_for_training(self, gray_frame: np.ndarray) -> list[tuple[int, int, int, int]]:
        if self.face_service is not None:
            try:
                faces = self.face_service.detect_faces(gray_frame)
                if faces:
                    return [tuple(map(int, f)) for f in faces]
            except Exception:
                pass
        if self._fallback_detector is None:
            return []
        try:
            return [
                tuple(map(int, f))
                for f in self._fallback_detector.detectMultiScale(gray_frame, 1.3, 5)
            ]
        except Exception:
            return []

    def rebuild_training_data(self, data_repo: DataRepository) -> tuple[list[np.ndarray], list[int]]:
        samples: list[np.ndarray] = []
        labels: list[int] = []
        backend_mode = self.current_backend_mode()
        deep_like_backend = backend_mode in {"deep", "lite"}

        self._refresh_service_labels()
        for user_id in sorted(self.state.user_dic.keys()):
            username = self.state.user_dic[user_id]
            for image_path in data_repo.iter_user_image_paths(user_id, username) or []:
                try:
                    from PIL import Image

                    img = Image.open(str(image_path)).convert("L")
                except Exception:
                    continue
                img_np = np.array(img)
                if img_np.size == 0:
                    continue
                if deep_like_backend:
                    # Deep/lite training computes embeddings from the whole sample.
                    # Skipping face re-detection here avoids duplicated heavy work.
                    samples.append(img_np)
                    labels.append(int(user_id))
                    continue
                faces = self._detect_faces_for_training(img_np)
                if not faces:
                    samples.append(img_np)
                    labels.append(int(user_id))
                    continue
                h_img, w_img = img_np.shape[:2]
                for (x, y, w, h) in faces:
                    x0 = max(0, int(x))
                    y0 = max(0, int(y))
                    x1 = min(w_img, x0 + max(1, int(w)))
                    y1 = min(h_img, y0 + max(1, int(h)))
                    if x1 <= x0 or y1 <= y0:
                        continue
                    crop = img_np[y0:y1, x0:x1]
                    if crop.size == 0:
                        continue
                    samples.append(crop)
                    labels.append(int(user_id))
        return samples, labels

    def train_and_save(self, samples: list[np.ndarray], labels: list[int]) -> bool:
        self._last_train_error = ""
        if len(samples) == 0 or len(samples) != len(labels):
            self._last_train_error = (
                f"invalid training data: samples={len(samples)}, labels={len(labels)}"
            )
            return False
        if not self.ensure_face_service_ready():
            self._last_train_error = self.face_service_error_text() or "face service not ready"
            return False
        self._refresh_service_labels()
        try:
            self.face_service.train(samples, labels)
            return True
        except Exception as exc:
            self._last_train_error = str(exc)
            return False

    def process_frame(self, gray_frame: np.ndarray, location: str) -> list[RecognitionEvent]:
        events: list[RecognitionEvent] = []
        if self.face_service is None:
            return events

        self._refresh_service_labels()
        try:
            predictions = self.face_service.recognize_frame(gray_frame)
        except Exception:
            return events

        for pred in predictions:
            x, y, w, h = pred["bbox"]
            name = pred.get("name", "unknown")
            if name == "unknown":
                continue

            emotion = "中性"
            if self.emotion is not None:
                try:
                    emotion, _ = self.emotion.predict(gray_frame[y : y + h, x : x + w])
                except Exception:
                    emotion = "中性"

            events.append(
                RecognitionEvent(
                    name=name,
                    emotion=emotion,
                    location=location,
                    timestamp=datetime.datetime.now().replace(microsecond=0),
                )
            )
        return events

    @staticmethod
    def persist_events(events: list[RecognitionEvent]) -> None:
        if not events:
            return
        db = sqls.SqlF()
        try:
            for event in events:
                db.saveNameTimePic(
                    event.name,
                    event.location,
                    event.timestamp,
                    emotion=event.emotion,
                )
        finally:
            db.dbclose()
