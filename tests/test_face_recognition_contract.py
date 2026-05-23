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
