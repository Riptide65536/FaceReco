from __future__ import annotations

import datetime
import os
import threading
import time
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
        self._frame_queue = Queue(maxsize=3)
        self._reader_thread = None
        self._reader_started = False
        self._stream_end_sentinel = object()
        self._frame_timeout_sentinel = object()
        self._pil_font = self._load_pil_font(28)
        self._haar_detector = cv2.CascadeClassifier(asset_path("haarcascade_frontalface_default.xml"))
        self._frame_index = 0
        self._predict_interval = max(1, int(os.getenv("FACE_RECO_DEEP_SKIP", "2")))
        self._last_predictions: list[dict] = []

        self.face_service = None
        try:
            if self._app_service.pipeline.ensure_face_service_ready():
                self.face_service = self._app_service.pipeline.face_service
                if self.face_service is not None:
                    self.face_service.labels = dict(self._app_service.state.user_dic)
            else:
                reason = self._app_service.pipeline.face_service_error_text() or "未知错误"
                _warn_once("face_backend_unavailable", "人脸识别模型不可用，实时识别将降级：", reason)
        except Exception as exc:
            _warn_once("face_backend_unavailable", "人脸识别模型不可用，实时识别将降级：", exc)
        self.detector = _DetectorAdapter(self)

        self.emotion = None
        try:
            self.emotion = EmotionRecognitionService()
        except Exception as exc:
            _warn_once("emotion_backend_unavailable", "情绪识别服务不可用，已降级为中性：", exc)

    @staticmethod
    def _sleep_frame_interval():
        time.sleep(0.01)

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
                self._frame_queue.put(frame, timeout=0.1)
            except Full:
                try:
                    _ = self._frame_queue.get_nowait()
                except Empty:
                    pass
                try:
                    self._frame_queue.put_nowait(frame)
                except Full:
                    pass

    def _get_frame(self):
        try:
            return self._frame_queue.get(timeout=0.3)
        except Empty:
            return self._frame_timeout_sentinel

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

    def _emit_frame(self, rgb_frame):
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
                _warn_once("recognition_model_load_failed", "识别模型加载失败：", exc)

        for frame in self._iter_frames():
            self._frame_index += 1
            frame_people = []
            rawframe = cv2.resize(frame, (640, 360))
            gray = cv2.cvtColor(rawframe, cv2.COLOR_BGR2GRAY)
            predictions = self._last_predictions
            if self.face_service is not None and (self._frame_index % self._predict_interval == 0):
                try:
                    self.face_service.labels = dict(self._app_service.state.user_dic)
                    predictions = self.face_service.recognize_frame(rawframe)
                except Exception:
                    predictions = []
                self._last_predictions = predictions

            rawframe = self._draw_text(rawframe, self.nameAndLocation, (7, 20), color=(0, 0, 255), font_scale=0.6, thickness=2)
            for pred in predictions:
                x, y, w, h = pred["bbox"]
                cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)
                name = pred.get("name", "unknown")
                confidence = pred.get("confidence")
                if debug_recognition:
                    print("name:", name)
                    print("confidence:", confidence)
                if model_loaded and (name != "unknown"):
                    face_gray = gray[y : y + h, x : x + w]
                    raw_emotion = "中性"
                    if self.emotion is not None:
                        try:
                            raw_emotion, _ = self.emotion.predict(face_gray)
                        except Exception:
                            raw_emotion = "中性"
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
                    rawframe = self._draw_text(rawframe, f"{name} | {emotion_text}", (x + 5, y + 15), color=(0, 0, 255), font_scale=1, thickness=2)
                    frame_people.append(f"{name}({emotion_text})")
                    face_list.append((name, emotion_text))
                    if (name, emotion_text) not in temp_face_list:
                        face_count_dic[(name, emotion_text)] = 1
                    else:
                        face_count_dic[(name, emotion_text)] += 1
                else:
                    rawframe = self._draw_text(rawframe, "unknown", (x + 5, y + 15), color=(0, 0, 255), font_scale=1, thickness=2)

            if frame_people:
                unique_people = []
                seen = set()
                for item in frame_people:
                    if item not in seen:
                        unique_people.append(item)
                        seen.add(item)
                summary_text = "当前帧识别: " + ", ".join(unique_people[:3])
                if len(unique_people) > 3:
                    summary_text += f" ... 共{len(unique_people)}人"
                rawframe = self._draw_text(rawframe, summary_text, (7, 45), color=(0, 0, 255), font_scale=0.6, thickness=2)

            rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
            if not self._running:
                break
            self._emit_frame(rawframe)

            for (name, emotion_text), count in face_count_dic.items():
                if count >= face_max_num:
                    now_datetime = str(datetime.datetime.now()).split(".")[0]
                    now_datetime = datetime.datetime.strptime(now_datetime, "%Y-%m-%d %H:%M:%S")
                    sql_repo.save_recognition_event(
                        name=name,
                        location=self.nameAndLocation,
                        timepoint=now_datetime,
                        emotion=emotion_text,
                    )
                    face_count_dic[(name, emotion_text)] = 0
            temp_face_list = face_list
            face_list = []
            self._sleep_frame_interval()

    def displaySimpleBrand(self):
        for frame in self._iter_frames():
            rawframe = cv2.resize(frame, (640, 360))
            faces = self.detector.detectMultiScale(rawframe, 1.3, 5)
            rawframe = self._draw_text(rawframe, self.nameAndLocation, (7, 20), color=(0, 0, 255), font_scale=0.6, thickness=2)
            for (x, y, w, h) in faces:
                cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)
            rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
            if not self._running:
                break
            self._emit_frame(rawframe)
            self._sleep_frame_interval()

    def displayJustdisplayBrand(self):
        for frame in self._iter_frames():
            rawframe = cv2.resize(frame, (640, 360))
            rawframe = self._draw_text(rawframe, self.nameAndLocation, (7, 20), color=(0, 0, 255), font_scale=0.6, thickness=2)
            rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
            if not self._running:
                break
            self._emit_frame(rawframe)
            self._sleep_frame_interval()

    def displayLuruBrand(self):
        for frame in self._iter_frames():
            rawframe = cv2.resize(frame, (640, 360))
            faces = self.detector.detectMultiScale(rawframe, 1.3, 5)
            rawframe = self._draw_text(rawframe, "人脸录入预览", (7, 20), color=(0, 0, 255), font_scale=0.6, thickness=2)
            for (x, y, w, h) in faces:
                cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)
            rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
            if not self._running:
                break
            self._emit_frame(rawframe)
            self._sleep_frame_interval()

    def close(self, release_system_lock=True):
        self._running = False
        if self.url == 0 and release_system_lock:
            self._app_service.state.system_lock_slot = 0
        if self.cap is not None:
            self.cap.release()
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.5)
        self._emit_no_signal()
