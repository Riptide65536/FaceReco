from __future__ import annotations

import datetime

import numpy as np

from app.services.recognition_pipeline import RecognitionPipeline
from app.state import AppState


class _FakeFaceService:
    def __init__(self):
        self.labels = {}
        self._trained = False

    def detect_faces(self, _frame):
        return [(0, 0, 16, 16)]

    def recognize_frame(self, _frame):
        return [
            {"bbox": (0, 0, 16, 16), "label": 1, "name": "linhao", "confidence": 92.0},
            {"bbox": (20, 20, 16, 16), "label": None, "name": "unknown", "confidence": 12.0},
        ]

    def train(self, samples, labels):
        assert len(samples) == len(labels)
        self._trained = True


class _FakeEmotionService:
    def predict(self, _face_gray):
        return "中性", 0.9


def test_pipeline_train_and_process_frame_with_fake_face_service(monkeypatch):
    state = AppState(user_dic={1: "linhao"})
    fake_service = _FakeFaceService()
    monkeypatch.setattr(RecognitionPipeline, "_create_face_service", lambda self: fake_service)
    pipeline = RecognitionPipeline(state)
    pipeline.emotion = _FakeEmotionService()

    samples = [np.zeros((32, 32), dtype="uint8")]
    labels = [1]
    assert pipeline.train_and_save(samples, labels) is True
    assert fake_service._trained is True

    frame = np.zeros((64, 64), dtype="uint8")
    events = pipeline.process_frame(frame, "test-location")
    assert len(events) == 1
    assert events[0].name == "linhao"
    assert events[0].emotion == "中性"
    assert events[0].location == "test-location"
    assert isinstance(events[0].timestamp, datetime.datetime)
