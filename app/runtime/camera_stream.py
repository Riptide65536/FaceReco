from __future__ import annotations

import datetime
import os
import threading
from queue import Empty, Full, Queue

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PySide2.QtCore import QObject, Qt, Signal
from PySide2.QtGui import QImage, QPixmap

from paths import asset_path
from services.emotion_service import EmotionRecognitionService


class _LabelBridge(QObject):
    pixmap_ready = Signal(QPixmap)

    def __init__(self, label):
        super().__init__()
        self._label = label
        self.pixmap_ready.connect(self._label.setPixmap, Qt.QueuedConnection)


class Camera:
    """Camera stream runtime with optional face recognition and emotion labels."""

    def __init__(self, url, outLabel, app_service, on_stream_end=None):
        self._app_service = app_service
        self.nameAndLocation = 'Test Video, No Location'
        self.displayMode = 0
        self.url = url
        self.outLabel = outLabel
        self._on_stream_end = on_stream_end
        self._bridge = _LabelBridge(outLabel)
        self._running = True
        self.cap = cv2.VideoCapture(self.url)
        self._frame_queue = Queue(maxsize=3)
        self._reader_thread = None
        self._reader_started = False
        self._stream_end_sentinel = object()
        self._frame_timeout_sentinel = object()
        self.detector = cv2.CascadeClassifier(asset_path('haarcascade_frontalface_default.xml'))
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self._pil_font = self._load_pil_font(28)
        self.emotion = None
        try:
            self.emotion = EmotionRecognitionService()
        except Exception as exc:
            print('情绪识别服务不可用，已回退为中性：', exc)

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
        if text == '':
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
        self._bridge.pixmap_ready.emit(QPixmap(asset_path('nosignal.png')))

    def display(self):
        sql_repo = self._app_service.sql_repo
        faceMaxNum = 5
        facecountDic = {}
        faceList = []
        tempfaceList = []
        emotion_state = {}
        debug_recognition = os.getenv('FACE_RECO_DEBUG', '0') == '1'

        model_loaded = False
        if self._app_service.data_repo.model_exists():
            self.recognizer.read(str(self._app_service.data_repo.model_file_path()))
            model_loaded = True
        self._start_frame_reader()

        while self._running and self.cap.isOpened():
            while self._running:
                frame = self._get_frame()
                if not self._running:
                    break
                if frame is self._frame_timeout_sentinel:
                    continue
                if frame is self._stream_end_sentinel:
                    self.cap.release()
                    self._emit_no_signal()
                    self._notify_stream_end()
                    print('released!')
                    break
                if frame is not None:
                    frame_people = []
                    rawframe = cv2.resize(frame, (640, 360))
                    frame = cv2.cvtColor(rawframe, cv2.COLOR_BGR2GRAY)
                    self.faces = self.detector.detectMultiScale(frame, 1.3, 5)
                    rawframe = self._draw_text(rawframe, self.nameAndLocation, (7, 20), color=(0, 0, 255), font_scale=0.6, thickness=2)
                    for (x, y, w, h) in self.faces:
                        cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)

                        if model_loaded:
                            idum, confidence = self.recognizer.predict(frame[y:y + h, x:x + w])
                            if debug_recognition:
                                print('idum为', idum)
                                print('confidence；', confidence)
                            if confidence < 68:
                                name = self._app_service.state.user_dic.get(idum, str(idum))
                                face_gray = frame[y:y + h, x:x + w]
                                raw_emotion = '中性'
                                if self.emotion is not None:
                                    try:
                                        raw_emotion, _ = self.emotion.predict(face_gray)
                                    except Exception:
                                        raw_emotion = '中性'
                                state = emotion_state.get(name, {'last_raw': '', 'stable': raw_emotion, 'count': 0})
                                if raw_emotion == state['last_raw']:
                                    state['count'] += 1
                                else:
                                    state['last_raw'] = raw_emotion
                                    state['count'] = 1
                                if state['count'] >= 2:
                                    state['stable'] = raw_emotion
                                emotion_state[name] = state
                                emotion_text = state['stable']
                                rawframe = self._draw_text(rawframe, f'{name} | {emotion_text}', (x + 5, y + 15), color=(0, 0, 255), font_scale=1, thickness=2)
                                frame_people.append(f'{name}({emotion_text})')
                                faceList.append((name, emotion_text))
                                if (name, emotion_text) not in tempfaceList:
                                    facecountDic[(name, emotion_text)] = 1
                                else:
                                    facecountDic[(name, emotion_text)] += 1
                            else:
                                rawframe = self._draw_text(rawframe, 'unknown', (x + 5, y + 15), color=(0, 0, 255), font_scale=1, thickness=2)

                    if frame_people:
                        unique_people = []
                        seen = set()
                        for item in frame_people:
                            if item not in seen:
                                unique_people.append(item)
                                seen.add(item)
                        summary_text = '当前帧识别: ' + ', '.join(unique_people[:3])
                        if len(unique_people) > 3:
                            summary_text += f' ... 共{len(unique_people)}人'
                        rawframe = self._draw_text(rawframe, summary_text, (7, 45), color=(0, 0, 255), font_scale=0.6, thickness=2)

                    rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
                    if not self._running:
                        break
                    self._emit_frame(rawframe)

                    for (name, emotion_text), count in facecountDic.items():
                        if count >= faceMaxNum:
                            nowdatetime = str(datetime.datetime.now()).split('.')[0]
                            nowdatetime = datetime.datetime.strptime(nowdatetime, '%Y-%m-%d %H:%M:%S')
                            sql_repo.save_recognition_event(
                                name=name,
                                location=self.nameAndLocation,
                                timepoint=nowdatetime,
                                emotion=emotion_text,
                            )
                            facecountDic[(name, emotion_text)] = 0
                    tempfaceList = faceList
                    faceList = []
                    cv2.waitKey(10)
            if not self._running:
                break

    def displaySimpleBrand(self):
        self._start_frame_reader()
        while self._running and self.cap.isOpened():
            while self._running:
                frame = self._get_frame()
                if not self._running:
                    break
                if frame is self._frame_timeout_sentinel:
                    continue
                if frame is self._stream_end_sentinel:
                    self.cap.release()
                    self._emit_no_signal()
                    self._notify_stream_end()
                    print('released!')
                    break
                if frame is not None:
                    rawframe = cv2.resize(frame, (640, 360))
                    frame = cv2.cvtColor(rawframe, cv2.COLOR_BGR2GRAY)
                    faces = self.detector.detectMultiScale(frame, 1.3, 5)
                    rawframe = self._draw_text(rawframe, self.nameAndLocation, (7, 20), color=(0, 0, 255), font_scale=0.6, thickness=2)
                    for (x, y, w, h) in faces:
                        cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)
                    rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
                    if not self._running:
                        break
                    self._emit_frame(rawframe)
                    cv2.waitKey(10)
            if not self._running:
                break

    def displayJustdisplayBrand(self):
        self._start_frame_reader()
        while self._running and self.cap.isOpened():
            while self._running:
                frame = self._get_frame()
                if not self._running:
                    break
                if frame is self._frame_timeout_sentinel:
                    continue
                if frame is self._stream_end_sentinel:
                    self.cap.release()
                    self._emit_no_signal()
                    self._notify_stream_end()
                    print('released!')
                    break
                if frame is not None:
                    rawframe = cv2.resize(frame, (640, 360))
                    rawframe = self._draw_text(rawframe, self.nameAndLocation, (7, 20), color=(0, 0, 255), font_scale=0.6, thickness=2)
                    rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
                    if not self._running:
                        break
                    self._emit_frame(rawframe)
                    cv2.waitKey(10)
            if not self._running:
                break

    def displayLuruBrand(self):
        self._start_frame_reader()
        while self._running and self.cap.isOpened():
            while self._running:
                frame = self._get_frame()
                if not self._running:
                    break
                if frame is self._frame_timeout_sentinel:
                    continue
                if frame is self._stream_end_sentinel:
                    self.cap.release()
                    self._emit_no_signal()
                    self._notify_stream_end()
                    print('released!')
                    break
                if frame is not None:
                    rawframe = cv2.resize(frame, (640, 360))
                    frame = cv2.cvtColor(rawframe, cv2.COLOR_BGR2GRAY)
                    faces = self.detector.detectMultiScale(frame, 1.3, 5)
                    rawframe = self._draw_text(rawframe, 'enroll in facial recognition', (7, 20), color=(0, 0, 255), font_scale=0.6, thickness=2)
                    for (x, y, w, h) in faces:
                        cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)
                    rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
                    if not self._running:
                        break
                    self._emit_frame(rawframe)
                    cv2.waitKey(10)
            if not self._running:
                break

    def close(self):
        self._running = False
        if self.url == 0:
            self._app_service.state.system_lock_slot = 0
        if self.cap is not None:
            self.cap.release()
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.5)
        self._emit_no_signal()
