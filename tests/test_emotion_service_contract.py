import numpy as np

from services.emotion_service import EmotionRecognitionService


def test_emotion_service_returns_neutral_without_model(tmp_path):
    missing_model = tmp_path / "missing_emotion_model.h5"
    service = EmotionRecognitionService(model_path=str(missing_model))
    face_gray = np.zeros((48, 48), dtype="uint8")
    emotion, score = service.predict(face_gray)
    assert emotion == "中性"
    assert score == 0.0
