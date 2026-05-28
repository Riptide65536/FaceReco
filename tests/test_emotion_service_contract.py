import sys
import types

import numpy as np

from services.emotion_service import EmotionRecognitionService


def test_emotion_service_returns_neutral_without_model(tmp_path):
    missing_model = tmp_path / "missing_emotion_model.h5"
    service = EmotionRecognitionService(model_path=str(missing_model))
    face_gray = np.zeros((48, 48), dtype="uint8")
    emotion, score = service.predict(face_gray)
    assert emotion == "中性"
    assert score == 0.0


def test_emotion_service_can_fallback_to_weights_only_model(monkeypatch, tmp_path):
    class _FakeModel:
        def __init__(self):
            self.loaded_weights = None

        def load_weights(self, path):
            self.loaded_weights = path

        @staticmethod
        def predict(_prepared, verbose=0):
            return np.asarray([[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]], dtype="float32")

    fake_model = _FakeModel()

    def _fake_load_model(_path, compile=False):
        raise ValueError("No model config found in the file")

    def _fake_sequential(_layers):
        return fake_model

    fake_models = types.ModuleType("tensorflow.keras.models")
    fake_models.load_model = _fake_load_model
    fake_models.Sequential = _fake_sequential

    fake_layers = types.ModuleType("tensorflow.keras.layers")
    fake_layers.Conv2D = lambda *args, **kwargs: ("conv2d", args, kwargs)
    fake_layers.Dense = lambda *args, **kwargs: ("dense", args, kwargs)
    fake_layers.Dropout = lambda *args, **kwargs: ("dropout", args, kwargs)
    fake_layers.Flatten = lambda *args, **kwargs: ("flatten", args, kwargs)
    fake_layers.MaxPooling2D = lambda *args, **kwargs: ("maxpool", args, kwargs)

    fake_tf = types.ModuleType("tensorflow")
    fake_keras = types.ModuleType("tensorflow.keras")
    fake_tf.keras = fake_keras
    fake_cv2 = types.ModuleType("cv2")
    fake_cv2.resize = lambda frame, size: np.zeros((size[1], size[0]), dtype="float32")

    monkeypatch.setitem(sys.modules, "tensorflow", fake_tf)
    monkeypatch.setitem(sys.modules, "tensorflow.keras", fake_keras)
    monkeypatch.setitem(sys.modules, "tensorflow.keras.models", fake_models)
    monkeypatch.setitem(sys.modules, "tensorflow.keras.layers", fake_layers)
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    model_path = tmp_path / "emotion_model.h5"
    model_path.write_bytes(b"weights-only")
    service = EmotionRecognitionService(model_path=str(model_path))

    face_gray = np.zeros((48, 48), dtype="uint8")
    emotion, score = service.predict(face_gray)

    assert fake_model.loaded_weights == str(model_path)
    assert service.model_format == "weights_only_h5"
    assert service.runtime_device == "CPU"
    assert emotion == "中性"
    assert score == 1.0
