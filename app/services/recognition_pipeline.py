from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from typing import Any

import numpy as np

import sqls
from app.repositories import DataRepository
from app.state import AppState
from paths import asset_path
from services.emotion_service import EmotionRecognitionService


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
        self.detector = None
        self.recognizer = None
        if self.cv2 is not None:
            self.detector = self.cv2.CascadeClassifier(asset_path("haarcascade_frontalface_default.xml"))
            self.recognizer = self.cv2.face.LBPHFaceRecognizer_create()
        self.emotion = None
        try:
            self.emotion = EmotionRecognitionService()
        except Exception:
            self.emotion = None
        self._load_model_if_exists()

    @staticmethod
    def _try_import_cv2():
        try:
            import cv2  # type: ignore

            return cv2
        except Exception:
            return None

    def _load_model_if_exists(self) -> None:
        yml = os.path.join("model", "model.yml")
        if (self.recognizer is not None) and os.path.exists(yml):
            try:
                self.recognizer.read(yml)
            except Exception:
                pass

    def rebuild_training_data(self, data_repo: DataRepository) -> tuple[list[np.ndarray], list[int]]:
        samples: list[np.ndarray] = []
        labels: list[int] = []
        if self.detector is None:
            return samples, labels
        if self.detector.empty():
            return samples, labels

        for user_id in sorted(self.state.user_dic.keys()):
            username = self.state.user_dic[user_id]
            for image_path in data_repo.iter_user_image_paths(user_id, username) or []:
                try:
                    from PIL import Image

                    img = Image.open(str(image_path)).convert("L")
                except Exception:
                    continue
                img_np = np.array(img)
                faces = self.detector.detectMultiScale(img_np)
                for (x, y, w, h) in faces:
                    samples.append(img_np[y : y + h, x : x + w])
                    labels.append(int(user_id))
        return samples, labels

    def train_and_save(self, samples: list[np.ndarray], labels: list[int]) -> bool:
        if self.cv2 is None:
            return False
        if len(samples) == 0 or len(samples) != len(labels):
            return False
        self.recognizer = self.cv2.face.LBPHFaceRecognizer_create()
        self.recognizer.train(samples, np.array(labels))
        os.makedirs("model", exist_ok=True)
        self.recognizer.write(os.path.join("model", "model.yml"))
        return True

    def process_frame(self, gray_frame: np.ndarray, location: str) -> list[RecognitionEvent]:
        events: list[RecognitionEvent] = []
        if self.detector is None or self.recognizer is None:
            return events
        faces = self.detector.detectMultiScale(gray_frame, 1.3, 5)
        for (x, y, w, h) in faces:
            name = "unknown"
            confidence = 999.0
            try:
                label, confidence = self.recognizer.predict(gray_frame[y : y + h, x : x + w])
                if confidence < self.confidence_threshold:
                    name = self.state.user_dic.get(int(label), str(label))
            except Exception:
                pass

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
