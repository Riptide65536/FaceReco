from __future__ import annotations

import datetime

import numpy as np

from app.services.recognition_pipeline import RecognitionPipeline
from app.state import AppState


class _FakeFaceService:
    def __init__(self):
        self.labels = {}
        self._trained = False
        self._mode = "deep"

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

    def backend_mode(self):
        return self._mode


class _FakeEmotionService:
    def predict(self, _face_gray):
        return "neutral", 0.9


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
    assert events[0].emotion == "neutral"
    assert events[0].location == "test-location"
    assert isinstance(events[0].timestamp, datetime.datetime)


def test_rebuild_training_data_skips_detection_for_deep_backend(monkeypatch, tmp_path):
    state = AppState(user_dic={1: "linhao"})
    fake_service = _FakeFaceService()
    fake_service._mode = "deep"
    monkeypatch.setattr(RecognitionPipeline, "_create_face_service", lambda self: fake_service)
    pipeline = RecognitionPipeline(state)

    data_dir = tmp_path / "data" / "linhao"
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
    except Exception:
        return
    sample_img = np.full((64, 64), 127, dtype=np.uint8)
    Image.fromarray(sample_img).save(str(data_dir / "1.jpg"))

    class _Repo:
        def iter_user_image_paths(self, _uid, _name):
            return [data_dir / "1.jpg"]

    pipeline._detect_faces_for_training = lambda _frame: (_ for _ in ()).throw(AssertionError("should not detect"))  # type: ignore[method-assign]
    samples, labels = pipeline.rebuild_training_data(_Repo())  # type: ignore[arg-type]
    assert len(samples) == 1
    assert labels == [1]
