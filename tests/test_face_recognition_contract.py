import sys
import types

import numpy as np
import pytest

import services.face_recognition_service as face_module
from services.face_detector import FaceDetection, YOLOFaceDetector
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
    monkeypatch.setattr(FaceRecognitionService, "_backend_error_message", None)

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
    monkeypatch.setattr(FaceRecognitionService, "_backend_error_message", None)

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


def test_yolo_face_detector_parses_ultralytics_predictions(monkeypatch, tmp_path):
    class _Tensor:
        def __init__(self, data):
            self._data = data

        def cpu(self):
            return self

        def numpy(self):
            return np.asarray(self._data, dtype="float32")

    class _Boxes:
        xyxy = _Tensor([[10, 20, 30, 50]])
        conf = _Tensor([0.9])

    class _Keypoints:
        xy = _Tensor([[[12, 22], [28, 22], [20, 31], [14, 40], [26, 40]]])

    class _Result:
        boxes = _Boxes()
        keypoints = _Keypoints()

    class _FakeYOLO:
        def __init__(self, path):
            self.path = path

        @staticmethod
        def predict(**_kwargs):
            return [_Result()]

    fake_ultralytics = types.ModuleType("ultralytics")
    fake_ultralytics.YOLO = _FakeYOLO
    monkeypatch.setitem(sys.modules, "ultralytics", fake_ultralytics)

    model_path = tmp_path / "yolov8n-face.pt"
    model_path.write_bytes(b"weights")

    detector = YOLOFaceDetector(model_path=str(model_path))
    detections = detector.detect(np.zeros((64, 64, 3), dtype="uint8"))

    assert len(detections) == 1
    assert detections[0].bbox == (10, 20, 20, 30)
    assert detections[0].score == pytest.approx(0.9)
    assert detections[0].kps is not None
    assert detections[0].kps.shape == (5, 2)


def test_face_recognition_service_keeps_deep_backend_when_yolo_detector_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(FaceRecognitionService, "_backend_error_message", None)

    class _FakeCv2:
        COLOR_BGR2GRAY = 6
        COLOR_GRAY2BGR = 8
        BORDER_REFLECT_101 = 4

        @staticmethod
        def cvtColor(frame, code):
            if code == _FakeCv2.COLOR_GRAY2BGR and len(frame.shape) == 2:
                return np.stack([frame, frame, frame], axis=-1)
            return frame

        @staticmethod
        def resize(frame, *_args, **_kwargs):
            return frame

        @staticmethod
        def copyMakeBorder(frame, *_args, **_kwargs):
            return frame

    class _FakeRecognizer:
        @staticmethod
        def get_feat(_frame):
            return np.ones((1, 4), dtype="float32")

    class _FakeAnalyzer:
        def __init__(self, *_args, **_kwargs):
            self.models = {"recognition": _FakeRecognizer()}

        @staticmethod
        def prepare(*_args, **_kwargs):
            return None

    class _BrokenYOLODetector:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("missing yolo model")

    class _FallbackDetector:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def detect(_frame):
            return [FaceDetection((1, 2, 30, 40))]

    fake_insightface = types.ModuleType("insightface")
    fake_insightface_app = types.ModuleType("insightface.app")
    fake_insightface_app.FaceAnalysis = _FakeAnalyzer
    fake_insightface.app = fake_insightface_app

    monkeypatch.setitem(sys.modules, "insightface", fake_insightface)
    monkeypatch.setitem(sys.modules, "insightface.app", fake_insightface_app)
    monkeypatch.setattr(face_module.FaceRecognitionService, "_load_cv2", staticmethod(lambda: _FakeCv2()))
    monkeypatch.setattr(
        face_module.FaceRecognitionService,
        "_resolve_ort_providers",
        staticmethod(lambda: ["CPUExecutionProvider"]),
    )
    monkeypatch.setattr(face_module, "YOLOFaceDetector", _BrokenYOLODetector)
    monkeypatch.setattr(face_module, "InsightFaceDetector", _FallbackDetector)

    service = face_module.FaceRecognitionService(model_path=str(tmp_path / "model.npz"))

    assert service.backend_mode() == "deep"
    assert service.detect_faces(np.zeros((32, 32), dtype="uint8")) == [(1, 2, 30, 40)]


def test_face_recognition_service_prefers_cuda_for_yolo_when_torch_has_gpu(monkeypatch):
    class _FakeCuda:
        @staticmethod
        def is_available():
            return True

    class _FakeTorch:
        cuda = _FakeCuda()

    monkeypatch.delenv("FACE_RECO_YOLO_DEVICE", raising=False)
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch())

    assert FaceRecognitionService._resolve_yolo_device() == "0"


def test_face_recognition_service_falls_back_to_cpu_for_yolo_when_torch_has_no_gpu(monkeypatch):
    class _FakeCuda:
        @staticmethod
        def is_available():
            return False

    class _FakeTorch:
        cuda = _FakeCuda()

    monkeypatch.delenv("FACE_RECO_YOLO_DEVICE", raising=False)
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch())

    assert FaceRecognitionService._resolve_yolo_device() == "cpu"


def test_face_recognition_service_aligns_five_point_keypoints_for_arcface(monkeypatch, tmp_path):
    class _FakeEmbedder:
        @staticmethod
        def get_feat(frame):
            assert frame.shape[:2] == (112, 112)
            return np.array([[1.0, 2.0, 3.0, 4.0]], dtype="float32")

    class _FakeCv2:
        COLOR_BGR2GRAY = 6
        COLOR_GRAY2BGR = 8

        @staticmethod
        def cvtColor(frame, code):
            if code == _FakeCv2.COLOR_GRAY2BGR and len(frame.shape) == 2:
                return np.stack([frame, frame, frame], axis=-1)
            return frame

        @staticmethod
        def resize(frame, size):
            return np.zeros((size[1], size[0], 3), dtype="uint8")

    fake_face_align = types.ModuleType("insightface.utils.face_align")
    fake_face_align.norm_crop = lambda _frame, landmark: np.zeros((112, 112, 3), dtype="uint8") + int(landmark.shape[0])
    fake_utils = types.ModuleType("insightface.utils")
    fake_utils.face_align = fake_face_align

    monkeypatch.setitem(sys.modules, "insightface.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "insightface.utils.face_align", fake_face_align)
    monkeypatch.setattr(FaceRecognitionService, "_backend_error_message", None)
    monkeypatch.setattr(FaceRecognitionService, "_load_cv2", staticmethod(lambda: _FakeCv2()))
    monkeypatch.setattr(FaceRecognitionService, "_init_backend_with_fallback", lambda self: None)

    service = FaceRecognitionService(model_path=str(tmp_path / "model.npz"))
    service._deep_embedder = _FakeEmbedder()
    service._deep_input_size = (112, 112)

    emb = service._extract_embedding_with_kps(
        np.zeros((64, 64, 3), dtype="uint8"),
        np.asarray([[1, 1], [2, 1], [1.5, 2], [1, 3], [2, 3]], dtype="float32"),
    )

    assert emb is not None
    assert emb.shape == (4,)
