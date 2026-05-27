from __future__ import annotations

import numpy as np
import pytest
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

from app.state import AppState
from services.face_recognition_service import FaceRecognitionService


def test_face_recognition_service_cache_helpers_work(tmp_path):
    pytest.importorskip("cv2")
    service = FaceRecognitionService(model_path=str(tmp_path / "model.npz"))
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    key = service._frame_cache_key(frame)
    assert key
    service._store_cached_predictions(frame, [{"bbox": (1, 2, 3, 4), "name": "alice"}])
    cached = service._cached_predictions(frame)
    assert cached is not None
    assert cached[0]["name"] == "alice"


def test_app_state_defaults_are_usable():
    state = AppState()
    assert isinstance(state.user_dic, dict)
    assert state.show_fps_overlay is False


def test_camera_motion_and_bbox_helpers():
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    gray1 = np.zeros((24, 24), dtype=np.uint8)
    gray2 = np.zeros((24, 24), dtype=np.uint8)
    gray2[8:12, 8:12] = 255
    assert Camera._motion_score(gray2, gray1) > 0
    bbox = Camera._scale_bbox((10, 20, 30, 40), (320, 180), (640, 360))
    assert bbox == (20, 40, 60, 80)


def test_camera_track_stabilizer_keeps_short_gaps():
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    camera = Camera.__new__(Camera)
    camera._prediction_tracks = []
    camera._next_track_id = 1
    camera._track_iou_threshold = 0.3
    camera._track_hold_frames = 3
    camera._track_max_misses = 5
    camera._track_ema_alpha = 0.5
    camera._track_center_match_ratio = 1.15
    camera._track_area_ratio_limit = 2.6
    camera._track_suppress_distance_ratio = 1.35
    camera._track_identity_hold_frames = 3
    camera._track_identity_keep_conf = 52.0
    camera._track_identity_switch_conf = 80.0

    first = camera._stabilize_predictions([{"bbox": (10, 10, 20, 20), "name": "alice", "confidence": 90}])
    assert first and first[0]["name"] == "alice"
    assert first[0]["track_id"] == 1
    second = camera._stabilize_predictions([{"bbox": (12, 12, 20, 20), "name": "alice", "confidence": 91}])
    assert second and second[0]["name"] == "alice"
    assert second[0]["track_id"] == 1
    assert second[0]["match_reason"] in {"steady", "iou", "center"}
    third = camera._stabilize_predictions([])
    assert third and third[0]["name"] == "alice"


def test_camera_track_stabilizer_keeps_identity_on_short_unknown_dips():
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    camera = Camera.__new__(Camera)
    camera._prediction_tracks = []
    camera._next_track_id = 1
    camera._track_iou_threshold = 0.3
    camera._track_hold_frames = 3
    camera._track_max_misses = 5
    camera._track_ema_alpha = 0.5
    camera._track_center_match_ratio = 1.15
    camera._track_area_ratio_limit = 2.6
    camera._track_suppress_distance_ratio = 1.35
    camera._track_identity_hold_frames = 3
    camera._track_identity_keep_conf = 52.0
    camera._track_identity_switch_conf = 80.0

    first = camera._stabilize_predictions(
        [{"bbox": (10, 10, 20, 20), "name": "alice", "label": 1, "confidence": 88.0}]
    )
    assert first and first[0]["name"] == "alice"

    second = camera._stabilize_predictions(
        [{"bbox": (12, 12, 20, 20), "name": "unknown", "label": 1, "confidence": 61.0}]
    )
    assert second and second[0]["name"] == "alice"


def test_camera_track_stabilizer_keeps_identity_during_detection_only_refresh():
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    camera = Camera.__new__(Camera)
    camera._prediction_tracks = []
    camera._next_track_id = 1
    camera._track_iou_threshold = 0.3
    camera._track_hold_frames = 3
    camera._track_max_misses = 5
    camera._track_ema_alpha = 0.5
    camera._track_center_match_ratio = 1.15
    camera._track_area_ratio_limit = 2.6
    camera._track_suppress_distance_ratio = 1.35
    camera._track_identity_hold_frames = 3
    camera._track_identity_keep_conf = 52.0
    camera._track_identity_switch_conf = 80.0

    first = camera._stabilize_predictions(
        [{"bbox": (10, 10, 20, 20), "name": "alice", "label": 1, "confidence": 88.0}]
    )
    assert first and first[0]["name"] == "alice"

    second = camera._stabilize_predictions(
        [{"bbox": (14, 12, 20, 20), "name": "unknown", "recognition_skipped": True}]
    )
    assert second and second[0]["name"] == "alice"
    assert second[0]["match_reason"] == "tracked"


def test_camera_track_stabilizer_merges_fast_motion_without_double_boxes():
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    camera = Camera.__new__(Camera)
    camera._prediction_tracks = []
    camera._next_track_id = 1
    camera._track_iou_threshold = 0.3
    camera._track_hold_frames = 3
    camera._track_max_misses = 5
    camera._track_ema_alpha = 0.5
    camera._track_center_match_ratio = 1.2
    camera._track_area_ratio_limit = 2.6
    camera._track_suppress_distance_ratio = 1.35
    camera._track_identity_hold_frames = 3
    camera._track_identity_keep_conf = 52.0
    camera._track_identity_switch_conf = 80.0

    first = camera._stabilize_predictions(
        [{"bbox": (100, 100, 80, 80), "name": "alice", "label": 1, "confidence": 90.0}]
    )
    assert len(first) == 1

    second = camera._stabilize_predictions(
        [{"bbox": (170, 100, 80, 80), "name": "alice", "label": 1, "confidence": 88.0}]
    )
    assert len(second) == 1
    assert second[0]["name"] == "alice"
    assert second[0]["track_id"] == 1


def test_camera_should_run_emotion_inference_respects_gap_and_cache():
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    camera = Camera.__new__(Camera)
    camera.emotion = object()
    camera._emotion_min_gap_s = 0.5
    camera._last_emotion_predict_ts = 0.0
    camera._emotion_cache = {}
    camera._emotion_cache_ttl = 2.0

    assert camera._should_run_emotion_inference("alice", 1.0) is True
    camera._last_emotion_predict_ts = 0.9
    assert camera._should_run_emotion_inference("alice", 1.1) is False
    camera._last_emotion_predict_ts = 0.0
    camera._emotion_cache["alice"] = {"emotion": "neutral", "ts": 1.0}
    assert camera._should_run_emotion_inference("alice", 2.0) is False


def test_camera_fps_overlay_helpers_respect_toggle():
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    camera = Camera.__new__(Camera)
    camera._show_fps_overlay = False
    camera._display_fps = 0.0
    camera._last_fps_sample_ts = 0.0

    camera.set_show_fps_overlay(True)
    assert camera._show_fps_overlay is True

    camera._record_emit_fps(1.0)
    camera._record_emit_fps(1.1)
    assert camera._display_fps > 0.0

    items: list[tuple[str, tuple[int, int], tuple[int, int, int], float, int]] = []
    camera._append_fps_overlay(np.zeros((360, 640, 3), dtype=np.uint8), items)
    assert items and items[0][0].startswith("FPS: ")


def test_camera_submit_detection_task_scales_boxes():
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    class _FakeFaceService:
        @staticmethod
        def detect_faces(_frame):
            return [(10, 20, 30, 40)]

    camera = Camera.__new__(Camera)
    camera.face_service = _FakeFaceService()
    camera._haar_detector = None
    camera._predict_pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = camera._submit_detection_task(
            np.zeros((180, 320, 3), dtype=np.uint8),
            (320, 180),
            (640, 360),
            "frame-key",
        )
        predicted, key = future.result(timeout=2.0)
    finally:
        camera._predict_pool.shutdown(wait=False, cancel_futures=True)

    assert key == "frame-key"
    assert predicted == [
        {
            "bbox": (20, 40, 60, 80),
            "label": None,
            "name": "unknown",
            "confidence": None,
            "recognition_skipped": True,
        }
    ]


def test_camera_get_frame_prefers_latest_frame():
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    camera = Camera.__new__(Camera)
    camera._frame_queue = Queue(maxsize=3)
    camera._latest_frame_only = True
    camera._frame_timeout_sentinel = object()

    camera._frame_queue.put_nowait("stale")
    camera._frame_queue.put_nowait("fresh")

    assert camera._get_frame() == "fresh"


def test_camera_should_run_full_recognition_uses_interval_and_force_refresh():
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    camera = Camera.__new__(Camera)
    camera.face_service = object()
    camera._frame_index = 1
    camera._last_predictions = [{"name": "alice"}]
    camera._last_recognition_ts = 10.0
    camera._recognition_interval = 3
    camera._recognition_min_gap_s = 0.2
    camera._recognition_force_refresh_s = 0.8

    assert camera._should_run_full_recognition(10.1) is False
    assert camera._should_run_full_recognition(10.9) is True

    camera._last_recognition_ts = 10.0
    camera._frame_index = 3
    assert camera._should_run_full_recognition(10.3) is True


def test_camera_runtime_mode_supports_realtime_30fps(monkeypatch):
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    monkeypatch.setenv("FACE_RECO_UI_FPS_REALTIME", "30")
    camera = Camera.__new__(Camera)
    camera.face_service = None
    camera._label_draw_interval = 1
    camera._summary_draw_interval = 1
    camera._emit_max_fps = 18.0
    camera._emit_min_gap_s = 1.0 / 18.0

    camera._apply_runtime_mode("realtime")

    assert camera._emit_max_fps == 30.0
    assert camera._emit_min_gap_s == pytest.approx(1.0 / 30.0)


def test_camera_runtime_mode_supports_unlimited_realtime_fps(monkeypatch):
    try:
        from app.runtime.camera_stream import Camera
    except ModuleNotFoundError:
        pytest.skip("PySide2 is not available in this test environment")

    monkeypatch.setenv("FACE_RECO_UI_FPS_REALTIME", "0")
    camera = Camera.__new__(Camera)
    camera.face_service = None
    camera._label_draw_interval = 1
    camera._summary_draw_interval = 1
    camera._emit_max_fps = 18.0
    camera._emit_min_gap_s = 1.0 / 18.0

    camera._apply_runtime_mode("realtime")

    assert camera._emit_max_fps == 0.0
    assert camera._emit_min_gap_s == 0.0
