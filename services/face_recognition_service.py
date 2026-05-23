from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional

if TYPE_CHECKING:
    import numpy as np


class FaceRecognitionService:
    """OpenCV Haar + LBPH face detection and recognition service."""

    def __init__(
        self,
        cascade_path: str = "attachment/haarcascade_frontalface_default.xml",
        model_path: str = "model/model.yml",
        confidence_threshold: float = 68.0,
        labels: Optional[dict[int, str]] = None,
    ) -> None:
        self.cascade_path = Path(cascade_path)
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold
        self.labels = labels or {}
        self.cv2 = self._load_cv2()
        self.detector = self.cv2.CascadeClassifier(str(self.cascade_path))
        self.recognizer = None
        if self.model_path.exists():
            self.load_model()

    @staticmethod
    def _load_cv2():
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError("OpenCV is not installed. Run: pip install -r requirements.txt") from exc
        if not hasattr(cv2, "face"):
            raise RuntimeError("opencv-contrib-python is required for LBPHFaceRecognizer.")
        return cv2

    def load_model(self) -> bool:
        self.recognizer = self.cv2.face.LBPHFaceRecognizer_create()
        self.recognizer.read(str(self.model_path))
        return True

    def detect_faces(self, frame: "np.ndarray") -> list[tuple[int, int, int, int]]:
        gray = self.to_gray(frame)
        faces = self.detector.detectMultiScale(gray, 1.3, 5)
        return [tuple(map(int, face)) for face in faces]

    def recognize_frame(self, frame: "np.ndarray") -> list[dict[str, Any]]:
        gray = self.to_gray(frame)
        results = []
        for x, y, w, h in self.detect_faces(gray):
            name = "unknown"
            confidence = None
            label = None
            if self.recognizer is not None:
                label, confidence = self.recognizer.predict(gray[y:y + h, x:x + w])
                if confidence < self.confidence_threshold:
                    name = self.labels.get(int(label), str(label))
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
        labels_array = np.array(list(labels))
        if not samples or len(samples) != len(labels_array):
            raise ValueError("Face samples and labels must be non-empty and have the same length.")
        recognizer = self.cv2.face.LBPHFaceRecognizer_create()
        recognizer.train(samples, labels_array)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        recognizer.write(str(self.model_path))
        self.recognizer = recognizer

    def to_gray(self, frame: "np.ndarray") -> "np.ndarray":
        if len(frame.shape) == 2:
            return frame
        return self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2GRAY)
