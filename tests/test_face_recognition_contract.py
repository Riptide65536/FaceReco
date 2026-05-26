import pytest

from services.face_recognition_service import FaceRecognitionService


def test_face_recognition_service_reports_missing_opencv_cleanly(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "cv2":
            raise ImportError("no cv2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="OpenCV is not installed"):
        FaceRecognitionService()


def test_face_recognition_service_falls_back_to_lbph_when_deep_unavailable(monkeypatch):
    import builtins

    class _FakeCascade:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def empty():
            return False

        @staticmethod
        def detectMultiScale(*_args, **_kwargs):
            return []

    class _FakeRecognizer:
        @staticmethod
        def read(*_args, **_kwargs):
            return None

        @staticmethod
        def save(*_args, **_kwargs):
            return None

        @staticmethod
        def train(*_args, **_kwargs):
            return None

        @staticmethod
        def predict(*_args, **_kwargs):
            return 0, 100.0

    class _FakeFaceModule:
        @staticmethod
        def LBPHFaceRecognizer_create():
            return _FakeRecognizer()

    class _FakeCv2:
        face = _FakeFaceModule()
        CascadeClassifier = _FakeCascade

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("insightface"):
            raise ImportError("no insightface")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(FaceRecognitionService, "_load_cv2", staticmethod(lambda: _FakeCv2()))
    service = FaceRecognitionService()
    assert service.backend_mode() == "lbph"


def test_face_recognition_service_falls_back_to_lite_when_deep_and_lbph_unavailable(monkeypatch):
    import builtins

    class _FakeCascade:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def empty():
            return False

        @staticmethod
        def detectMultiScale(*_args, **_kwargs):
            return []

    class _FakeCv2NoFace:
        CascadeClassifier = _FakeCascade
        face = None
        COLOR_BGR2GRAY = 6
        COLOR_GRAY2BGR = 8
        FONT_HERSHEY_SIMPLEX = 0

        @staticmethod
        def cvtColor(frame, _code):
            return frame

        @staticmethod
        def resize(frame, _size):
            return frame

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("insightface"):
            raise ImportError("no insightface")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(FaceRecognitionService, "_load_cv2", staticmethod(lambda: _FakeCv2NoFace()))
    service = FaceRecognitionService()
    assert service.backend_mode() == "lite"
