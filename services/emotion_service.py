from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Optional

import numpy as np


class EmotionRecognitionService:
    """Keras emotion classifier with small multi-frame smoothing buffer."""

    EMOTIONS = ["高兴", "悲伤", "愤怒", "惊讶", "恐惧", "厌恶", "中性"]

    def __init__(self, model_path: str = "model/emotion_model.h5", window_size: int = 5) -> None:
        self.model_path = Path(model_path)
        self.window: deque[np.ndarray] = deque(maxlen=window_size)
        self.model = self._load_model() if self.model_path.exists() else None

    def _load_model(self):
        try:
            from tensorflow.keras.models import load_model
        except ImportError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError("TensorFlow/Keras is required for emotion recognition.") from exc
        return load_model(str(self.model_path))

    def predict(self, face_gray: np.ndarray) -> tuple[str, float]:
        if self.model is None:
            return "中性", 0.0
        prepared = self._preprocess(face_gray)
        probs = np.asarray(self.model.predict(prepared, verbose=0)[0], dtype="float32")
        self.window.append(probs)
        fused = np.mean(np.stack(tuple(self.window), axis=0), axis=0)
        index = int(np.argmax(fused))
        return self.EMOTIONS[index], float(fused[index])

    @staticmethod
    def _preprocess(face_gray: np.ndarray) -> np.ndarray:
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("OpenCV is required for emotion preprocessing.") from exc
        face = cv2.resize(face_gray, (48, 48)).astype("float32") / 255.0
        return face.reshape(1, 48, 48, 1)
