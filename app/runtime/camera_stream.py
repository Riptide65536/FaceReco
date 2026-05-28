from __future__ import annotations

import datetime
import hashlib
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Empty, Full, Queue

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PySide2.QtCore import QObject, Qt, Signal
from PySide2.QtGui import QImage, QPixmap

from paths import asset_path
from services.emotion_service import EmotionRecognitionService

_WARNED_FLAGS: set[str] = set()
_WARN_LOCK = threading.Lock()
_DEBUG_VERBOSE = os.getenv("FACE_RECO_VERBOSE", "0") == "1"


def _warn_once(flag: str, message: str, *extra) -> None:
    with _WARN_LOCK:
        if flag in _WARNED_FLAGS:
            return
        _WARNED_FLAGS.add(flag)
    print(message, *extra)


class _LabelBridge(QObject):
    pixmap_ready = Signal(QPixmap)

    def __init__(self, label):
        super().__init__()
        self._label = label
        self.pixmap_ready.connect(self._label.setPixmap, Qt.QueuedConnection)


class _DetectorAdapter:
    """Compatibility adapter exposing detectMultiScale for legacy callers."""

    def __init__(self, camera_obj):
        self._camera = camera_obj

    def detectMultiScale(self, frame, *_args, **_kwargs):
        if getattr(self._camera, "_prefer_haar_detector", False):
            service = None
        else:
            service = self._camera.face_service
        faces = []
        if service is not None:
            try:
                faces = service.detect_faces(frame)
            except Exception:
                faces = []
        if faces:
            return faces
        haar = self._camera._haar_detector
        if haar is None:
            return []
        try:
            gray = frame if len(frame.shape) == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return [tuple(map(int, f)) for f in haar.detectMultiScale(gray, 1.3, 5)]
        except Exception:
            return []


class Camera:
    """Camera stream runtime with optional face recognition and emotion labels."""

    def __init__(self, url, outLabel, app_service, on_stream_end=None, prefer_haar_detector=False):
        self._app_service = app_service
        self.nameAndLocation = "Test Video, No Location"
        self.displayMode = 0
        self.url = url
        self.outLabel = outLabel
        self._on_stream_end = on_stream_end
        self._prefer_haar_detector = bool(prefer_haar_detector)
        self._bridge = _LabelBridge(outLabel)
        self._running = True
        self.cap = cv2.VideoCapture(self.url)
        self._configure_capture_for_low_latency()
        self._latest_frame_only = os.getenv("FACE_RECO_LATEST_FRAME_ONLY", "1") != "0"
        self._frame_queue = Queue(maxsize=max(1, int(os.getenv("FACE_RECO_FRAME_QUEUE", "1"))))
        self._reader_thread = None
        self._reader_started = False
        self._stream_end_sentinel = object()
        self._frame_timeout_sentinel = object()
        self._pil_font = self._load_pil_font(28)
        self._haar_detector = cv2.CascadeClassifier(asset_path("haarcascade_frontalface_default.xml"))
        self._frame_index = 0
        self._predict_interval = max(1, int(os.getenv("FACE_RECO_DEEP_SKIP", "2")))
        self._predict_min_gap_s = max(0.0, float(os.getenv("FACE_RECO_PREDICT_MIN_GAP", "0.12")))
        self._force_refresh_s = max(self._predict_min_gap_s, float(os.getenv("FACE_RECO_FORCE_REFRESH", "1.2")))
        self._analysis_width = max(240, int(os.getenv("FACE_RECO_ANALYSIS_WIDTH", "480")))
        self._motion_threshold = max(0.0, float(os.getenv("FACE_RECO_MIN_MOTION", "2.5")))
        self._last_predict_ts = 0.0
        self._last_recognition_ts = 0.0
        self._last_analysis_gray_small: np.ndarray | None = None
        self._last_predictions: list[dict] = []
        self._last_prediction_key = ""
        self._predict_task_kind = ""
        self._next_track_id = 1
        self._track_iou_threshold = max(0.05, min(0.9, float(os.getenv("FACE_RECO_TRACK_IOU", "0.30"))))
        self._track_hold_frames = max(0, int(os.getenv("FACE_RECO_TRACK_HOLD_FRAMES", "3")))
        self._track_max_misses = max(self._track_hold_frames, int(os.getenv("FACE_RECO_TRACK_MAX_MISSES", "5")))
        self._track_ema_alpha = min(1.0, max(0.2, float(os.getenv("FACE_RECO_TRACK_ALPHA", "0.65"))))
        self._track_center_match_ratio = max(0.4, float(os.getenv("FACE_RECO_TRACK_CENTER_RATIO", "1.15")))
        self._track_area_ratio_limit = max(1.1, float(os.getenv("FACE_RECO_TRACK_AREA_RATIO", "2.6")))
        self._track_suppress_distance_ratio = max(0.5, float(os.getenv("FACE_RECO_TRACK_SUPPRESS_RATIO", "1.35")))
        self._track_identity_hold_frames = max(1, int(os.getenv("FACE_RECO_IDENTITY_HOLD_FRAMES", "3")))
        self._track_identity_keep_conf = max(0.0, min(100.0, float(os.getenv("FACE_RECO_IDENTITY_KEEP_CONF", "52.0"))))
        self._track_identity_switch_conf = max(
            self._track_identity_keep_conf,
            min(100.0, float(os.getenv("FACE_RECO_IDENTITY_SWITCH_CONF", "80.0"))),
        )
        self._prediction_tracks: list[dict[str, object]] = []
        self._emotion_cache: dict[str, dict[str, object]] = {}
        self._emotion_cache_ttl = max(0.5, float(os.getenv("FACE_RECO_EMOTION_TTL", "2.0")))
        self._emotion_min_gap_s = max(0.0, float(os.getenv("FACE_RECO_EMOTION_MIN_GAP", "0.35")))
        self._emotion_default_label = os.getenv("FACE_RECO_EMOTION_DEFAULT", "中性").strip() or "中性"
        self._recognition_interval = max(1, int(os.getenv("FACE_RECO_RECOGNIZE_INTERVAL", "2")))
        self._recognition_min_gap_s = max(0.0, float(os.getenv("FACE_RECO_RECOGNIZE_MIN_GAP", "0.18")))
        self._recognition_force_refresh_s = max(
            self._recognition_min_gap_s,
            float(os.getenv("FACE_RECO_RECOGNIZE_FORCE_REFRESH", "0.75")),
        )
        self._last_emotion_predict_ts = 0.0
        self._label_draw_interval = max(1, int(os.getenv("FACE_RECO_LABEL_SKIP", "2")))
        self._summary_draw_interval = max(1, int(os.getenv("FACE_RECO_SUMMARY_SKIP", "4")))
        self._emit_max_fps = max(5.0, float(os.getenv("FACE_RECO_UI_FPS", "18")))
        self._emit_min_gap_s = 0.0 if self._emit_max_fps <= 0 else (1.0 / self._emit_max_fps)
        self._last_emit_ts = 0.0
        self._last_fps_sample_ts = 0.0
        self._display_fps = 0.0
        self._show_fps_overlay = bool(getattr(self._app_service.state, "show_fps_overlay", False))
        self._predict_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="face-predict")
        self._predict_future: Future | None = None
        self._emotion_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="emotion-predict")
        self._emotion_future: Future | None = None
        self._emotion_future_name = ""

        self.face_service = None
        try:
            if self._app_service.pipeline.ensure_face_service_ready():
                self.face_service = self._app_service.pipeline.face_service
                if self.face_service is not None:
                    self.face_service.labels = dict(self._app_service.state.user_dic)
            else:
                reason = self._app_service.pipeline.face_service_error_text() or "鏈煡閿欒"
                _warn_once("face_backend_unavailable", "浜鸿劯璇嗗埆妯″瀷涓嶅彲鐢紝瀹炴椂璇嗗埆灏嗛檷绾э細", reason)
        except Exception as exc:
            _warn_once("face_backend_unavailable", "浜鸿劯璇嗗埆妯″瀷涓嶅彲鐢紝瀹炴椂璇嗗埆灏嗛檷绾э細", exc)
        self.detector = _DetectorAdapter(self)

        self.emotion = None
        try:
            self.emotion = EmotionRecognitionService()
        except Exception as exc:
            _warn_once("emotion_backend_unavailable", "鎯呯华璇嗗埆鏈嶅姟涓嶅彲鐢紝宸查檷绾т负涓€э細", exc)
        self._apply_runtime_mode(getattr(self._app_service.state, "realtime_mode", "balanced"))

    @staticmethod
    def _sleep_frame_interval():
        time.sleep(0.01)

    def _configure_capture_for_low_latency(self) -> None:
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

    def _apply_runtime_mode(self, mode):
        mode = str(mode or "balanced").strip().lower()
        realtime_fps_override = float(os.getenv("FACE_RECO_UI_FPS_REALTIME", "30"))
        balanced_fps_override = float(os.getenv("FACE_RECO_UI_FPS_BALANCED", "18"))
        accurate_fps_override = float(os.getenv("FACE_RECO_UI_FPS_ACCURATE", "15"))
        presets = {
            "realtime": {
                "predict_interval": 1,
                "predict_min_gap_s": 0.05,
                "force_refresh_s": 0.30,
                "analysis_width": 320,
                "motion_threshold": 1.8,
                "emotion_ttl": 3.0,
                "emotion_min_gap_s": 1.50,
                "recognition_interval": 4,
                "recognition_min_gap_s": 0.22,
                "recognition_force_refresh_s": 0.80,
                "track_hold_frames": 2,
                "track_max_misses": 3,
                "track_alpha": 0.55,
                "label_draw_interval": 2,
                "summary_draw_interval": 3,
                "emit_max_fps": realtime_fps_override,
            },
            "balanced": {
                "predict_interval": 2,
                "predict_min_gap_s": 0.12,
                "force_refresh_s": 1.2,
                "analysis_width": 448,
                "motion_threshold": 2.5,
                "emotion_ttl": 2.0,
                "emotion_min_gap_s": 0.35,
                "recognition_interval": 2,
                "recognition_min_gap_s": 0.22,
                "recognition_force_refresh_s": 0.90,
                "track_hold_frames": 3,
                "track_max_misses": 5,
                "track_alpha": 0.65,
                "label_draw_interval": 2,
                "summary_draw_interval": 4,
                "emit_max_fps": balanced_fps_override,
            },
            "accurate": {
                "predict_interval": 3,
                "predict_min_gap_s": 0.20,
                "force_refresh_s": 2.0,
                "analysis_width": 640,
                "motion_threshold": 3.5,
                "emotion_ttl": 3.0,
                "emotion_min_gap_s": 0.20,
                "recognition_interval": 1,
                "recognition_min_gap_s": 0.20,
                "recognition_force_refresh_s": 0.45,
                "track_hold_frames": 4,
                "track_max_misses": 6,
                "track_alpha": 0.75,
                "label_draw_interval": 1,
                "summary_draw_interval": 2,
                "emit_max_fps": accurate_fps_override,
            },
        }
        preset = presets.get(mode, presets["balanced"])
        self._runtime_mode = mode
        self._predict_interval = max(1, int(preset["predict_interval"]))
        self._predict_min_gap_s = max(0.0, float(preset["predict_min_gap_s"]))
        self._force_refresh_s = max(self._predict_min_gap_s, float(preset["force_refresh_s"]))
        self._analysis_width = max(240, int(preset["analysis_width"]))
        self._motion_threshold = max(0.0, float(preset["motion_threshold"]))
        self._emotion_cache_ttl = max(0.5, float(preset["emotion_ttl"]))
        self._emotion_min_gap_s = max(0.0, float(preset["emotion_min_gap_s"]))
        self._recognition_interval = max(1, int(preset["recognition_interval"]))
        self._recognition_min_gap_s = max(0.0, float(preset["recognition_min_gap_s"]))
        self._recognition_force_refresh_s = max(
            self._recognition_min_gap_s,
            float(preset["recognition_force_refresh_s"]),
        )
        self._track_hold_frames = max(0, int(preset["track_hold_frames"]))
        self._track_max_misses = max(self._track_hold_frames, int(preset["track_max_misses"]))
        self._track_ema_alpha = min(1.0, max(0.2, float(preset["track_alpha"])))
        self._label_draw_interval = max(1, int(preset["label_draw_interval"]))
        self._summary_draw_interval = max(1, int(preset["summary_draw_interval"]))
        self._emit_max_fps = float(preset["emit_max_fps"])
        self._emit_min_gap_s = 0.0 if self._emit_max_fps <= 0 else (1.0 / self._emit_max_fps)

        if self.face_service is not None and hasattr(self.face_service, "set_realtime_mode"):
            try:
                self.face_service.set_realtime_mode(mode)
            except Exception:
                pass

        # Deep+CPU-only backend needs stronger throttling to keep UI smooth.
        if self._is_deep_cpu_only():
            self._analysis_width = min(self._analysis_width, 320)
            self._predict_interval = max(self._predict_interval, 3)
            self._predict_min_gap_s = max(self._predict_min_gap_s, 0.12)
            self._force_refresh_s = max(self._force_refresh_s, 0.55)
            self._recognition_interval = max(self._recognition_interval, 4)
            self._recognition_min_gap_s = max(self._recognition_min_gap_s, 0.30)
            self._recognition_force_refresh_s = max(self._recognition_force_refresh_s, 1.10)
            self._emotion_cache_ttl = max(self._emotion_cache_ttl, 3.5)
            self._emotion_min_gap_s = max(self._emotion_min_gap_s, 2.0)
            self._label_draw_interval = max(self._label_draw_interval, 3)
            self._summary_draw_interval = max(self._summary_draw_interval, 6)
            if self._runtime_mode != "realtime":
                if self._emit_max_fps > 0:
                    self._emit_max_fps = min(self._emit_max_fps, 14.0)
                else:
                    self._emit_max_fps = 14.0
            self._emit_min_gap_s = 0.0 if self._emit_max_fps <= 0 else (1.0 / self._emit_max_fps)

    def set_runtime_mode(self, mode):
        self._apply_runtime_mode(mode)

    def set_show_fps_overlay(self, enabled: bool) -> None:
        self._show_fps_overlay = bool(enabled)

    def _record_emit_fps(self, now: float) -> None:
        if self._last_fps_sample_ts > 0.0:
            delta = max(1e-6, now - self._last_fps_sample_ts)
            instant_fps = 1.0 / delta
            if self._display_fps <= 0.0:
                self._display_fps = instant_fps
            else:
                self._display_fps = (self._display_fps * 0.8) + (instant_fps * 0.2)
        self._last_fps_sample_ts = now

    def _append_fps_overlay(
        self,
        frame_bgr: np.ndarray,
        text_items: list[tuple[str, tuple[int, int], tuple[int, int, int], float, int]],
    ) -> None:
        if not self._show_fps_overlay:
            return
        height = int(frame_bgr.shape[0]) if getattr(frame_bgr, "shape", None) is not None else 0
        y = max(24, height - 12)
        text_items.append((f"FPS: {self._display_fps:.1f}", (8, y), (80, 220, 120), 0.7, 2))

    def _is_deep_cpu_only(self) -> bool:
        if self.face_service is None:
            return False
        try:
            backend = str(self.face_service.backend_mode())
        except Exception:
            backend = ""
        if backend != "deep":
            return False
        providers = list(getattr(self.face_service, "_deep_providers", []) or [])
        if not providers:
            return True
        return ("CUDAExecutionProvider" not in providers) and ("TensorrtExecutionProvider" not in providers)

    def _start_frame_reader(self):
        if self._reader_started:
            return
        self._reader_started = True
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _reader_loop(self):
        while self._running and self.cap.isOpened():
            ok, frame = self.cap.read()
            if not ok:
                try:
                    self._frame_queue.put_nowait(self._stream_end_sentinel)
                except Full:
                    pass
                break
            try:
                self._frame_queue.put(frame, timeout=0.02)
            except Full:
                try:
                    while True:
                        _ = self._frame_queue.get_nowait()
                        if not self._latest_frame_only:
                            break
                except Empty:
                    pass
                try:
                    self._frame_queue.put_nowait(frame)
                except Empty:
                    pass
                except Full:
                    pass

    def _get_frame(self):
        try:
            frame = self._frame_queue.get(timeout=0.3)
        except Empty:
            return self._frame_timeout_sentinel
        if not self._latest_frame_only:
            return frame
        latest = frame
        while True:
            try:
                newest = self._frame_queue.get_nowait()
            except Empty:
                break
            latest = newest
        return latest

    def _notify_stream_end(self):
        if callable(self._on_stream_end):
            try:
                self._on_stream_end(self)
            except Exception:
                pass

    @staticmethod
    def _load_pil_font(size=28):
        candidates = [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\simsun.ttc",
        ]
        for path in candidates:
            try:
                if os.path.exists(path):
                    return ImageFont.truetype(path, size=size)
            except Exception:
                continue
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _draw_text(self, frame_bgr, text, org, color=(0, 0, 255), font_scale=0.8, thickness=2):
        text = str(text)
        if text == "":
            return frame_bgr
        if all(ord(ch) < 128 for ch in text) or self._pil_font is None:
            cv2.putText(frame_bgr, text, org, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
            return frame_bgr

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        draw = ImageDraw.Draw(pil_img)
        rgb_color = (int(color[2]), int(color[1]), int(color[0]))
        draw.text((int(org[0]), int(org[1]) - 24), text, fill=rgb_color, font=self._pil_font)
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    def _draw_text_batch(self, frame_bgr: np.ndarray, items: list[tuple[str, tuple[int, int], tuple[int, int, int], float, int]]) -> np.ndarray:
        if not items:
            return frame_bgr
        if all((text and all(ord(ch) < 128 for ch in str(text))) for text, _, _, _, _ in items):
            for text, org, color, font_scale, thickness in items:
                cv2.putText(frame_bgr, str(text), org, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
            return frame_bgr
        if self._pil_font is None:
            for text, org, color, font_scale, thickness in items:
                cv2.putText(frame_bgr, str(text), org, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
            return frame_bgr
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        draw = ImageDraw.Draw(pil_img)
        for text, org, color, _, _ in items:
            rgb_color = (int(color[2]), int(color[1]), int(color[0]))
            draw.text((int(org[0]), int(org[1]) - 24), str(text), fill=rgb_color, font=self._pil_font)
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    def _submit_prediction_task(self, analysis_frame: np.ndarray, src_size: tuple[int, int], dst_size: tuple[int, int], frame_signature: str):
        if self.face_service is None:
            return None
        labels = dict(self._app_service.state.user_dic)

        def _job():
            self.face_service.labels = labels
            preds = self.face_service.recognize_frame(analysis_frame)
            if src_size != dst_size:
                src_w, src_h = src_size
                dst_w, dst_h = dst_size
                preds = [
                    {
                        **pred,
                        "bbox": self._scale_bbox(tuple(map(int, pred["bbox"])), (src_w, src_h), (dst_w, dst_h)),
                    }
                    for pred in preds
                ]
            return preds, frame_signature

        return self._predict_pool.submit(_job)

    def _submit_detection_task(
        self,
        analysis_frame: np.ndarray,
        src_size: tuple[int, int],
        dst_size: tuple[int, int],
        frame_signature: str,
    ):
        def _job():
            if self.face_service is not None:
                boxes = self.face_service.detect_faces(analysis_frame)
            elif self._haar_detector is not None:
                gray = analysis_frame if len(analysis_frame.shape) == 2 else cv2.cvtColor(analysis_frame, cv2.COLOR_BGR2GRAY)
                boxes = [tuple(map(int, f)) for f in self._haar_detector.detectMultiScale(gray, 1.3, 5)]
            else:
                boxes = []
            predictions = [
                {
                    "bbox": tuple(map(int, box)),
                    "label": None,
                    "name": "unknown",
                    "confidence": None,
                    "recognition_skipped": True,
                }
                for box in boxes
            ]
            if src_size != dst_size:
                src_w, src_h = src_size
                dst_w, dst_h = dst_size
                predictions = [
                    {
                        **pred,
                        "bbox": self._scale_bbox(tuple(map(int, pred["bbox"])), (src_w, src_h), (dst_w, dst_h)),
                    }
                    for pred in predictions
                ]
            return predictions, frame_signature

        return self._predict_pool.submit(_job)

    def _should_run_full_recognition(self, now_ts: float) -> bool:
        elapsed = now_ts - self._last_recognition_ts
        if self._last_recognition_ts <= 0.0:
            return True
        if elapsed >= self._recognition_force_refresh_s:
            return True
        if elapsed < self._recognition_min_gap_s:
            return False
        if not self._last_predictions:
            return True
        if any(str(pred.get("name", "unknown")) == "unknown" for pred in self._last_predictions):
            return True
        return (self._frame_index % self._recognition_interval) == 0

    def _should_run_emotion_inference(self, name: str, now_ts: float) -> bool:
        if self.emotion is None:
            return False
        if name == "unknown":
            return False
        emotion_future = getattr(self, "_emotion_future", None)
        if emotion_future is not None and (not emotion_future.done()):
            return False
        if (now_ts - self._last_emotion_predict_ts) < self._emotion_min_gap_s:
            return False
        cache_entry = self._emotion_cache.get(name)
        if cache_entry and (now_ts - float(cache_entry.get("ts", 0.0))) <= self._emotion_cache_ttl:
            return False
        return True

    def _collect_emotion_result(self) -> None:
        emotion_future = getattr(self, "_emotion_future", None)
        if emotion_future is None or (not emotion_future.done()):
            return
        try:
            name, emotion_text, predicted_ts = emotion_future.result()
            if name:
                self._emotion_cache[name] = {"emotion": emotion_text, "ts": float(predicted_ts)}
                self._last_emotion_predict_ts = float(predicted_ts)
        except Exception:
            pass
        finally:
            self._emotion_future = None
            self._emotion_future_name = ""

    def _submit_emotion_task(self, name: str, face_gray: np.ndarray, now_ts: float) -> None:
        if self.emotion is None:
            return
        emotion_future = getattr(self, "_emotion_future", None)
        if emotion_future is not None and (not emotion_future.done()):
            return
        face_copy = np.ascontiguousarray(face_gray.copy())

        def _job():
            try:
                emotion_text, _ = self.emotion.predict(face_copy)
            except Exception:
                emotion_text = self._emotion_default_label
            return name, emotion_text, now_ts

        self._emotion_future_name = name
        self._emotion_future = self._emotion_pool.submit(_job)

    @staticmethod
    def _core_attendance_types() -> set[str]:
        return {"上班打卡", "下班打卡", "外出登记"}

    def _save_detected_recognition_event(self, sql_repo, name: str, emotion_text: str, now_datetime: datetime.datetime) -> bool:
        if not name or name == "unknown":
            return False
        state = getattr(self._app_service, "state", None)
        custom_label = state.active_custom_attendance_label() if state is not None else ""
        if not custom_label:
            return bool(
                sql_repo.save_recognition_event(
                    name=name,
                    location=self.nameAndLocation,
                    timepoint=now_datetime,
                    emotion=emotion_text,
                )
            )
        if not state.try_mark_custom_attendance_recorded(name):
            return False

        daily_types = set(sql_repo.get_daily_attendance_types(name, now_datetime))
        has_core_attendance = bool(daily_types & self._core_attendance_types())
        if not has_core_attendance:
            sql_repo.save_recognition_event(
                name=name,
                location=self.nameAndLocation,
                timepoint=now_datetime,
                emotion=emotion_text,
            )

        saved_custom = bool(
            sql_repo.save_recognition_event(
                name=name,
                location=self.nameAndLocation,
                timepoint=now_datetime,
                emotion=emotion_text,
                attendance_type=custom_label,
            )
        )
        if not saved_custom:
            state.unmark_custom_attendance_recorded(name)
        return saved_custom

    @staticmethod
    def _shutdown_executor(executor) -> None:
        if executor is None:
            return
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)
        except Exception:
            pass

    @staticmethod
    def _resize_for_analysis(frame_bgr: np.ndarray, target_width: int) -> np.ndarray:
        if target_width <= 0:
            return frame_bgr
        h, w = frame_bgr.shape[:2]
        if w <= target_width:
            return frame_bgr
        target_height = max(1, int(h * target_width / float(w)))
        return cv2.resize(frame_bgr, (target_width, target_height))

    @staticmethod
    def _motion_score(gray_now: np.ndarray, gray_prev: np.ndarray | None) -> float:
        if gray_prev is None:
            return float("inf")
        if gray_now.shape != gray_prev.shape:
            return float("inf")
        diff = cv2.absdiff(gray_now, gray_prev)
        return float(np.mean(diff))

    @staticmethod
    def _frame_signature(gray_frame: np.ndarray) -> str:
        try:
            small = cv2.resize(gray_frame, (32, 18))
            return hashlib.blake2b(small.tobytes(), digest_size=8).hexdigest()
        except Exception:
            return ""

    @staticmethod
    def _scale_bbox(
        bbox: tuple[int, int, int, int],
        src_size: tuple[int, int],
        dst_size: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        src_w, src_h = src_size
        dst_w, dst_h = dst_size
        if src_w <= 0 or src_h <= 0:
            return bbox
        sx = dst_w / float(src_w)
        sy = dst_h / float(src_h)
        x, y, w, h = bbox
        return (
            int(round(x * sx)),
            int(round(y * sy)),
            max(1, int(round(w * sx))),
            max(1, int(round(h * sy))),
        )

    @staticmethod
    def _bbox_iou(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
        lx, ly, lw, lh = left
        rx, ry, rw, rh = right
        l_x1, l_y1, l_x2, l_y2 = lx, ly, lx + lw, ly + lh
        r_x1, r_y1, r_x2, r_y2 = rx, ry, rx + rw, ry + rh
        ix1 = max(l_x1, r_x1)
        iy1 = max(l_y1, r_y1)
        ix2 = min(l_x2, r_x2)
        iy2 = min(l_y2, r_y2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = float((ix2 - ix1) * (iy2 - iy1))
        area_l = float(max(1, lw) * max(1, lh))
        area_r = float(max(1, rw) * max(1, rh))
        return inter / max(1.0, area_l + area_r - inter)

    @staticmethod
    def _bbox_center_distance(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
        lx, ly, lw, lh = left
        rx, ry, rw, rh = right
        lc_x = lx + (lw / 2.0)
        lc_y = ly + (lh / 2.0)
        rc_x = rx + (rw / 2.0)
        rc_y = ry + (rh / 2.0)
        return float(((lc_x - rc_x) ** 2 + (lc_y - rc_y) ** 2) ** 0.5)

    @staticmethod
    def _bbox_area_ratio(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
        lw, lh = max(1, int(left[2])), max(1, int(left[3]))
        rw, rh = max(1, int(right[2])), max(1, int(right[3]))
        left_area = float(lw * lh)
        right_area = float(rw * rh)
        larger = max(left_area, right_area)
        smaller = max(1.0, min(left_area, right_area))
        return larger / smaller

    def _track_match_score(self, bbox: tuple[int, int, int, int], track_bbox: tuple[int, int, int, int]) -> float:
        iou = self._bbox_iou(bbox, track_bbox)
        center_distance = self._bbox_center_distance(bbox, track_bbox)
        max_dim = float(max(bbox[2], bbox[3], track_bbox[2], track_bbox[3], 1))
        normalized_center = center_distance / max_dim
        area_ratio = self._bbox_area_ratio(bbox, track_bbox)

        if iou >= self._track_iou_threshold:
            return iou + 1.0
        if normalized_center <= self._track_center_match_ratio and area_ratio <= self._track_area_ratio_limit:
            center_score = max(0.01, (self._track_center_match_ratio - normalized_center) / max(0.01, self._track_center_match_ratio))
            area_score = max(0.01, 1.0 - min(1.0, (area_ratio - 1.0) / max(0.1, self._track_area_ratio_limit - 1.0)))
            return 0.25 + (center_score * 0.5) + (area_score * 0.25)
        return -1.0

    def _track_match_reason(self, bbox: tuple[int, int, int, int], track_bbox: tuple[int, int, int, int]) -> str:
        iou = self._bbox_iou(bbox, track_bbox)
        if iou >= self._track_iou_threshold:
            return "iou"
        return "center"

    def _next_track_identifier(self) -> int:
        track_id = int(self._next_track_id)
        self._next_track_id += 1
        return track_id

    def _should_suppress_stale_track(
        self,
        stale_bbox: tuple[int, int, int, int],
        active_bbox: tuple[int, int, int, int],
    ) -> bool:
        if self._bbox_iou(stale_bbox, active_bbox) >= 0.35:
            return True
        center_distance = self._bbox_center_distance(stale_bbox, active_bbox)
        max_dim = float(max(stale_bbox[2], stale_bbox[3], active_bbox[2], active_bbox[3], 1))
        normalized_center = center_distance / max_dim
        if normalized_center <= self._track_suppress_distance_ratio:
            return True
        return False

    def _stabilize_predictions(self, predictions: list[dict]) -> list[dict]:
        if not predictions and not self._prediction_tracks:
            return []

        updated_tracks: list[dict[str, object]] = []
        unmatched_tracks = [dict(track) for track in self._prediction_tracks]

        for pred in predictions:
            bbox = tuple(map(int, pred.get("bbox", (0, 0, 0, 0))))
            best_idx = -1
            best_score = -1.0
            for idx, track in enumerate(unmatched_tracks):
                track_bbox = tuple(map(int, track.get("bbox", (0, 0, 0, 0))))
                score = self._track_match_score(bbox, track_bbox)
                if score > best_score:
                    best_score = score
                    best_idx = idx

            if best_idx >= 0 and best_score >= 0.0:
                track = unmatched_tracks.pop(best_idx)
                old_bbox = tuple(map(int, track.get("bbox", bbox)))
                match_reason = self._track_match_reason(bbox, old_bbox)
                blended_bbox = tuple(
                    int(round(old * (1.0 - self._track_ema_alpha) + new * self._track_ema_alpha))
                    for old, new in zip(old_bbox, bbox)
                )
                stabilized = self._stabilize_track_identity(track, pred)
                track.update(
                    {
                        "bbox": blended_bbox,
                        "name": stabilized.get("name", track.get("name", "unknown")),
                        "label": stabilized.get("label", track.get("label")),
                        "confidence": stabilized.get("confidence", track.get("confidence")),
                        "identity_hold": stabilized.get("identity_hold", track.get("identity_hold", 0)),
                        "pending_name": stabilized.get("pending_name", track.get("pending_name", "")),
                        "pending_label": stabilized.get("pending_label", track.get("pending_label")),
                        "switch_streak": stabilized.get("switch_streak", track.get("switch_streak", 0)),
                        "track_id": track.get("track_id", self._next_track_identifier()),
                        "match_reason": stabilized.get("match_reason", match_reason),
                        "similarity": stabilized.get("similarity", pred.get("similarity")),
                        "misses": 0,
                    }
                )
                updated_tracks.append(track)
            else:
                updated_tracks.append(
                    {
                        "bbox": bbox,
                        "name": pred.get("name", "unknown"),
                        "label": pred.get("label"),
                        "confidence": pred.get("confidence"),
                        "identity_hold": 0,
                        "pending_name": "",
                        "pending_label": None,
                        "switch_streak": 0,
                        "track_id": self._next_track_identifier(),
                        "match_reason": "new",
                        "similarity": pred.get("similarity"),
                        "misses": 0,
                    }
                )

        for track in unmatched_tracks:
            misses = int(track.get("misses", 0)) + 1
            track_bbox = tuple(map(int, track.get("bbox", (0, 0, 0, 0))))
            if any(
                self._should_suppress_stale_track(
                    track_bbox,
                    tuple(map(int, active.get("bbox", (0, 0, 0, 0)))),
                )
                for active in updated_tracks
            ):
                continue
            if misses <= self._track_max_misses and str(track.get("name", "unknown")) != "unknown":
                track["misses"] = misses
                track["match_reason"] = "hold"
                updated_tracks.append(track)

        stable_predictions = [
            {
                "bbox": tuple(map(int, track.get("bbox", (0, 0, 0, 0)))),
                "name": str(track.get("name", "unknown")),
                "label": track.get("label"),
                "similarity": track.get("similarity"),
                "confidence": track.get("confidence"),
                "track_id": track.get("track_id"),
                "match_reason": str(track.get("match_reason", "")),
            }
            for track in updated_tracks
            if int(track.get("misses", 0)) <= self._track_hold_frames
        ]
        # Keep only one box per recognized name and drop heavy-overlap boxes.
        best_by_name: dict[str, dict] = {}
        unknown_preds: list[dict] = []
        for pred in stable_predictions:
            name = str(pred.get("name", "unknown"))
            if name == "unknown":
                unknown_preds.append(pred)
                continue
            score = float(pred.get("confidence") or 0.0)
            old = best_by_name.get(name)
            old_score = float(old.get("confidence") or 0.0) if old else -1.0
            if (old is None) or (score >= old_score):
                best_by_name[name] = pred

        merged = list(best_by_name.values()) + unknown_preds
        deduped: list[dict] = []
        for pred in merged:
            bbox = tuple(map(int, pred.get("bbox", (0, 0, 0, 0))))
            overlapped = False
            for kept in deduped:
                kept_bbox = tuple(map(int, kept.get("bbox", (0, 0, 0, 0))))
                if (
                    self._bbox_iou(bbox, kept_bbox) >= 0.65
                    or self._should_suppress_stale_track(bbox, kept_bbox)
                ):
                    overlapped = True
                    break
            if not overlapped:
                deduped.append(pred)

        self._prediction_tracks = updated_tracks
        return deduped

    def _stabilize_track_identity(self, track: dict[str, object], pred: dict) -> dict[str, object]:
        prev_name = str(track.get("name", "unknown"))
        prev_label = track.get("label")
        prev_conf = float(track.get("confidence") or 0.0)
        prev_hold = int(track.get("identity_hold", 0))
        pending_name = str(track.get("pending_name", ""))
        pending_label = track.get("pending_label")
        switch_streak = int(track.get("switch_streak", 0))

        name = str(pred.get("name", "unknown"))
        label = pred.get("label")
        confidence = pred.get("confidence")
        conf_value = float(confidence or 0.0)
        similarity = pred.get("similarity")
        recognition_skipped = bool(pred.get("recognition_skipped", False))

        same_label = (
            prev_label is not None
            and label is not None
            and int(prev_label) == int(label)
        )

        if recognition_skipped:
            if prev_name != "unknown":
                return {
                    "name": prev_name,
                    "label": prev_label,
                    "similarity": track.get("similarity"),
                    "confidence": prev_conf,
                    "identity_hold": prev_hold + 1,
                    "pending_name": "",
                    "pending_label": None,
                    "switch_streak": 0,
                    "match_reason": "tracked",
                }
            return {
                "name": "unknown",
                "label": prev_label,
                "similarity": track.get("similarity"),
                "confidence": prev_conf if prev_conf > 0.0 else confidence,
                "identity_hold": prev_hold,
                "pending_name": "",
                "pending_label": None,
                "switch_streak": 0,
                "match_reason": "tracked-unknown",
            }

        if prev_name != "unknown":
            if name == "unknown":
                if same_label or conf_value >= self._track_identity_keep_conf or prev_hold < self._track_identity_hold_frames:
                    return {
                        "name": prev_name,
                        "label": prev_label,
                        "similarity": similarity if similarity is not None else track.get("similarity"),
                        "confidence": max(prev_conf, conf_value) if confidence is not None else prev_conf,
                        "identity_hold": prev_hold + 1,
                        "pending_name": "",
                        "pending_label": None,
                        "switch_streak": 0,
                        "match_reason": "hold",
                    }
                return {
                    "name": name,
                    "label": label,
                    "similarity": similarity,
                    "confidence": confidence,
                    "identity_hold": 0,
                    "pending_name": "",
                    "pending_label": None,
                    "switch_streak": 0,
                    "match_reason": "unknown",
                }

            if name != prev_name:
                if same_label:
                    return {
                        "name": prev_name,
                        "label": prev_label,
                        "similarity": similarity if similarity is not None else track.get("similarity"),
                        "confidence": max(prev_conf, conf_value),
                        "identity_hold": 0,
                        "pending_name": "",
                        "pending_label": None,
                        "switch_streak": 0,
                        "match_reason": "same-label",
                    }
                if conf_value < self._track_identity_switch_conf:
                    next_streak = switch_streak + 1 if (pending_name == name and pending_label == label) else 1
                    if next_streak < 2:
                        return {
                            "name": prev_name,
                            "label": prev_label,
                            "similarity": similarity if similarity is not None else track.get("similarity"),
                            "confidence": max(prev_conf, conf_value),
                            "identity_hold": 0,
                            "pending_name": name,
                            "pending_label": label,
                            "switch_streak": next_streak,
                            "match_reason": "pending-switch",
                        }
                return {
                    "name": name,
                    "label": label,
                    "similarity": similarity,
                    "confidence": confidence,
                    "identity_hold": 0,
                    "pending_name": "",
                    "pending_label": None,
                    "switch_streak": 0,
                    "match_reason": "switch",
                }

            return {
                "name": name,
                "label": label,
                "similarity": similarity,
                "confidence": confidence,
                "identity_hold": 0,
                "pending_name": "",
                "pending_label": None,
                "switch_streak": 0,
                "match_reason": "steady",
            }

        return {
            "name": name,
            "label": label,
            "similarity": similarity,
            "confidence": confidence,
            "identity_hold": 0,
            "pending_name": "",
            "pending_label": None,
            "switch_streak": 0,
            "match_reason": "fresh",
        }

    def _append_prediction_debug_overlay(
        self,
        text_items: list[tuple[str, tuple[int, int], tuple[int, int, int], float, int]],
        pred: dict,
        x: int,
        y: int,
    ) -> None:
        track_id = pred.get("track_id")
        if track_id is None:
            return
        similarity = pred.get("similarity")
        sim_text = "--"
        if similarity is not None:
            try:
                sim_text = f"{float(similarity):.2f}"
            except Exception:
                sim_text = str(similarity)
        match_reason = str(pred.get("match_reason", ""))
        debug_text = f"T{track_id} s:{sim_text} {match_reason}"
        text_items.append((debug_text, (x + 5, max(18, y + 36)), (0, 255, 255), 0.55, 1))

    def _emit_frame(self, rgb_frame):
        now = time.monotonic()
        if self._emit_min_gap_s > 0.0 and (now - self._last_emit_ts) < self._emit_min_gap_s:
            return
        self._last_emit_ts = now
        self._record_emit_fps(now)
        img = QImage(
            rgb_frame.data,
            rgb_frame.shape[1],
            rgb_frame.shape[0],
            rgb_frame.shape[1] * 3,
            QImage.Format_RGB888,
        )
        self._bridge.pixmap_ready.emit(QPixmap.fromImage(img))

    def _emit_no_signal(self):
        self._bridge.pixmap_ready.emit(QPixmap(asset_path("nosignal.png")))

    def _iter_frames(self):
        self._start_frame_reader()
        while self._running and self.cap.isOpened():
            frame = self._get_frame()
            if not self._running:
                break
            if frame is self._frame_timeout_sentinel:
                continue
            if frame is self._stream_end_sentinel:
                self.cap.release()
                self._emit_no_signal()
                self._notify_stream_end()
                if _DEBUG_VERBOSE:
                    print("released!")
                break
            if frame is None:
                continue
            yield frame

    def display(self):
        sql_repo = self._app_service.sql_repo
        face_max_num = 5
        face_count_dic = {}
        face_list = []
        temp_face_list = []
        emotion_state = {}
        debug_recognition = os.getenv("FACE_RECO_DEBUG", "0") == "1"

        model_loaded = False
        if (self.face_service is not None) and self._app_service.data_repo.model_exists():
            try:
                self.face_service.load_model()
                self.face_service.labels = dict(self._app_service.state.user_dic)
                model_loaded = True
            except Exception as exc:
                _warn_once("recognition_model_load_failed", "recognition model load failed:", exc)

        for frame in self._iter_frames():
            self._frame_index += 1
            frame_people = []
            self._collect_emotion_result()
            rawframe = cv2.resize(frame, (640, 360))
            analysis_frame = self._resize_for_analysis(rawframe, self._analysis_width)
            gray = cv2.cvtColor(rawframe, cv2.COLOR_BGR2GRAY)
            analysis_gray = cv2.cvtColor(analysis_frame, cv2.COLOR_BGR2GRAY)
            now_ts = time.monotonic()
            elapsed = now_ts - self._last_predict_ts
            motion_score = self._motion_score(analysis_gray, self._last_analysis_gray_small)
            frame_signature = self._frame_signature(analysis_gray)
            is_new_frame = frame_signature != self._last_prediction_key
            should_predict = (
                self.face_service is not None
                and (
                    elapsed >= self._force_refresh_s
                    or (elapsed >= self._predict_min_gap_s and is_new_frame and motion_score >= self._motion_threshold)
                    or (self._frame_index % self._predict_interval == 0 and elapsed >= self._predict_min_gap_s)
                )
            )

            if self._predict_future is not None and self._predict_future.done():
                try:
                    predicted, key = self._predict_future.result()
                    predicted = self._stabilize_predictions(predicted)
                    self._last_predictions = predicted
                    self._last_predict_ts = now_ts
                    self._last_prediction_key = str(key)
                    if self._predict_task_kind == "recognize":
                        self._last_recognition_ts = now_ts
                except Exception:
                    pass
                finally:
                    self._predict_future = None
                    self._predict_task_kind = ""

            if should_predict and self._predict_future is None:
                src_h, src_w = analysis_frame.shape[:2]
                dst_h, dst_w = rawframe.shape[:2]
                if self._should_run_full_recognition(now_ts):
                    self._predict_future = self._submit_prediction_task(
                        analysis_frame.copy(),
                        (src_w, src_h),
                        (dst_w, dst_h),
                        frame_signature,
                    )
                    self._predict_task_kind = "recognize"
                else:
                    self._predict_future = self._submit_detection_task(
                        analysis_frame.copy(),
                        (src_w, src_h),
                        (dst_w, dst_h),
                        frame_signature,
                    )
                    self._predict_task_kind = "detect"
                self._last_analysis_gray_small = analysis_gray.copy()

            predictions = self._last_predictions
            text_items: list[tuple[str, tuple[int, int], tuple[int, int, int], float, int]] = []
            text_items.append((self.nameAndLocation, (7, 20), (0, 0, 255), 0.6, 2))
            for pred in predictions:
                x, y, w, h = pred["bbox"]
                cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)
                name = pred.get("name", "unknown")
                confidence = pred.get("confidence")
                if debug_recognition:
                    print(
                        "pred:",
                        {
                            "track_id": pred.get("track_id"),
                            "name": name,
                            "similarity": pred.get("similarity"),
                            "confidence": confidence,
                            "match_reason": pred.get("match_reason"),
                            "bbox": pred.get("bbox"),
                        },
                    )
                if model_loaded and (name != "unknown"):
                    face_gray = gray[y : y + h, x : x + w]
                    now_emotion_ts = time.monotonic()
                    cache_entry = self._emotion_cache.get(name)
                    raw_emotion = self._emotion_default_label
                    if cache_entry and (now_emotion_ts - float(cache_entry.get("ts", 0.0))) <= self._emotion_cache_ttl:
                        raw_emotion = str(cache_entry.get("emotion", self._emotion_default_label))
                    elif self._should_run_emotion_inference(name, now_emotion_ts):
                        self._submit_emotion_task(name, face_gray, now_emotion_ts)

                    state = emotion_state.get(name, {"last_raw": "", "stable": raw_emotion, "count": 0})
                    if raw_emotion == state["last_raw"]:
                        state["count"] += 1
                    else:
                        state["last_raw"] = raw_emotion
                        state["count"] = 1
                    if state["count"] >= 2:
                        state["stable"] = raw_emotion
                    emotion_state[name] = state
                    emotion_text = state["stable"]
                    text_items.append((f"{name} | {emotion_text}", (x + 5, y + 15), (0, 0, 255), 1.0, 2))
                    if debug_recognition:
                        self._append_prediction_debug_overlay(text_items, pred, x, y)
                    frame_people.append(f"{name}({emotion_text})")
                    face_list.append((name, emotion_text))
                    if (name, emotion_text) not in temp_face_list:
                        face_count_dic[(name, emotion_text)] = 1
                    else:
                        face_count_dic[(name, emotion_text)] += 1
                else:
                    text_items.append(("unknown", (x + 5, y + 15), (0, 0, 255), 1.0, 2))
                    if debug_recognition:
                        self._append_prediction_debug_overlay(text_items, pred, x, y)

            if frame_people:
                unique_people = []
                seen = set()
                for item in frame_people:
                    if item not in seen:
                        unique_people.append(item)
                        seen.add(item)
                summary_text = "Current detections: " + ", ".join(unique_people[:3])
                if len(unique_people) > 3:
                    summary_text += f" ... total {len(unique_people)}"
                text_items.append((summary_text, (7, 45), (0, 0, 255), 0.6, 2))

            self._append_fps_overlay(rawframe, text_items)
            rawframe = self._draw_text_batch(rawframe, text_items)

            rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
            if not self._running:
                break
            self._emit_frame(rawframe)

            for (name, emotion_text), count in face_count_dic.items():
                if count >= face_max_num:
                    now_datetime = str(datetime.datetime.now()).split(".")[0]
                    now_datetime = datetime.datetime.strptime(now_datetime, "%Y-%m-%d %H:%M:%S")
                    self._save_detected_recognition_event(sql_repo, name, emotion_text, now_datetime)
                    face_count_dic[(name, emotion_text)] = 0
            temp_face_list = face_list
            face_list = []
            self._sleep_frame_interval()

    def displaySimpleBrand(self):
        for frame in self._iter_frames():
            self._frame_index += 1
            rawframe = cv2.resize(frame, (640, 360))
            analysis_frame = self._resize_for_analysis(rawframe, self._analysis_width)
            analysis_gray = cv2.cvtColor(analysis_frame, cv2.COLOR_BGR2GRAY)
            now_ts = time.monotonic()
            elapsed = now_ts - self._last_predict_ts
            motion_score = self._motion_score(analysis_gray, self._last_analysis_gray_small)
            frame_signature = self._frame_signature(analysis_gray)
            is_new_frame = frame_signature != self._last_prediction_key
            should_detect = (
                elapsed >= self._force_refresh_s
                or (elapsed >= self._predict_min_gap_s and is_new_frame and motion_score >= self._motion_threshold)
                or (self._frame_index % self._predict_interval == 0 and elapsed >= self._predict_min_gap_s)
            )

            if self._predict_future is not None and self._predict_future.done():
                try:
                    predicted, key = self._predict_future.result()
                    self._last_predictions = self._stabilize_predictions(predicted)
                    self._last_predict_ts = now_ts
                    self._last_prediction_key = str(key)
                except Exception:
                    pass
                finally:
                    self._predict_future = None
                    self._predict_task_kind = ""

            if should_detect and self._predict_future is None:
                src_h, src_w = analysis_frame.shape[:2]
                dst_h, dst_w = rawframe.shape[:2]
                self._predict_future = self._submit_detection_task(
                    analysis_frame.copy(),
                    (src_w, src_h),
                    (dst_w, dst_h),
                    frame_signature,
                )
                self._predict_task_kind = "detect"
                self._last_analysis_gray_small = analysis_gray.copy()

            text_items = [(self.nameAndLocation, (7, 20), (0, 0, 255), 0.6, 2)]
            for pred in self._last_predictions:
                x, y, w, h = tuple(map(int, pred.get("bbox", (0, 0, 0, 0))))
                cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)
            self._append_fps_overlay(rawframe, text_items)
            rawframe = self._draw_text_batch(rawframe, text_items)
            rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
            if not self._running:
                break
            self._emit_frame(rawframe)
            self._sleep_frame_interval()

    def displayJustdisplayBrand(self):
        for frame in self._iter_frames():
            rawframe = cv2.resize(frame, (640, 360))
            text_items = [(self.nameAndLocation, (7, 20), (0, 0, 255), 0.6, 2)]
            self._append_fps_overlay(rawframe, text_items)
            rawframe = self._draw_text_batch(rawframe, text_items)
            rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
            if not self._running:
                break
            self._emit_frame(rawframe)
            self._sleep_frame_interval()

    def displayLuruBrand(self):
        for frame in self._iter_frames():
            rawframe = cv2.resize(frame, (640, 360))
            faces = self.detector.detectMultiScale(rawframe, 1.3, 5)
            text_items = [("人脸录入预览", (7, 20), (0, 0, 255), 0.6, 2)]
            for (x, y, w, h) in faces:
                cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)
            self._append_fps_overlay(rawframe, text_items)
            rawframe = self._draw_text_batch(rawframe, text_items)
            rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
            if not self._running:
                break
            self._emit_frame(rawframe)
            self._sleep_frame_interval()

    def close(self, release_system_lock=True):
        self._running = False
        future = getattr(self, "_predict_future", None)
        if future is not None and (not future.done()):
            future.cancel()
        self._predict_future = None
        predict_pool = getattr(self, "_predict_pool", None)
        self._shutdown_executor(predict_pool)
        emotion_future = getattr(self, "_emotion_future", None)
        if emotion_future is not None and (not emotion_future.done()):
            emotion_future.cancel()
        self._emotion_future = None
        emotion_pool = getattr(self, "_emotion_pool", None)
        self._shutdown_executor(emotion_pool)
        if self.url == 0 and release_system_lock:
            self._app_service.state.system_lock_slot = 0
        if self.cap is not None:
            self.cap.release()
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.5)
        self._emit_no_signal()
