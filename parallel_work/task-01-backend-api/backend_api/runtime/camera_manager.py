from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend_api.adapters.legacy_app import LegacyAppAdapter
from backend_api.core.websocket import WebSocketClosed, WebSocketConnection
from backend_api.models import (
    AlertResult,
    DetectionResult,
    EmotionResult,
    EventEnvelope,
    FramePacket,
    RecognitionResult,
    RuntimeFace,
    VisionObservation,
)


@dataclass
class CameraSession:
    camera_id: str
    source: str
    name_location: str
    display_mode: int
    running: bool = False
    frame_id: int = 0
    fps: float = 0.0
    last_error: str = ""
    started_at: datetime | None = None
    last_frame_at: datetime | None = None
    latest_faces: list[RuntimeFace] = field(default_factory=list)
    latest_packet: dict[str, Any] | None = None
    latest_observation: dict[str, Any] | None = None
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _stream_subscribers: set[WebSocketConnection] = field(default_factory=set, repr=False)
    _stream_lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _dedupe_cache: dict[str, float] = field(default_factory=dict, repr=False)


class CameraManager:
    def __init__(self, adapter: LegacyAppAdapter) -> None:
        self.adapter = adapter
        self._lock = threading.RLock()
        self._sessions: dict[str, CameraSession] = {}
        self._event_subscribers: set[WebSocketConnection] = set()
        self._event_lock = threading.RLock()
        self._persist_interval_seconds = 10.0

    def shutdown(self) -> None:
        for camera_id in list(self._sessions.keys()):
            self.stop_camera(camera_id)
        with self._event_lock:
            subscribers = list(self._event_subscribers)
            self._event_subscribers.clear()
        for subscriber in subscribers:
            subscriber.close()

    def runtime_snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            snapshot: dict[str, dict[str, Any]] = {}
            for camera_id, session in self._sessions.items():
                snapshot[camera_id] = {
                    "running": session.running,
                    "frame_id": session.frame_id,
                    "fps": session.fps,
                    "last_error": session.last_error,
                    "started_at": session.started_at,
                    "last_frame_at": session.last_frame_at,
                }
            return snapshot

    def start_camera(self, camera_id: str, source: str, name_location: str, display_mode: int) -> dict[str, Any]:
        with self._lock:
            existing = self._sessions.get(camera_id)
            if existing and existing.running:
                raise RuntimeError(f"Camera {camera_id} is already running.")
            session = CameraSession(
                camera_id=str(camera_id),
                source=str(source),
                name_location=str(name_location),
                display_mode=int(display_mode),
                running=True,
                started_at=datetime.now(),
            )
            session._thread = threading.Thread(
                target=self._camera_loop,
                name=f"camera-session-{camera_id}",
                args=(session,),
                daemon=True,
            )
            self._sessions[camera_id] = session
            session._thread.start()
            return self.runtime_snapshot().get(camera_id, {})

    def stop_camera(self, camera_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(str(camera_id))
            if session is None:
                return False
            session.running = False
            session._stop.set()
            thread = session._thread
        if thread is not None:
            thread.join(timeout=2.0)
        with self._lock:
            session = self._sessions.pop(str(camera_id), None)
        if session is None:
            return False
        with session._stream_lock:
            subscribers = list(session._stream_subscribers)
            session._stream_subscribers.clear()
        for subscriber in subscribers:
            subscriber.close()
        return True

    def add_stream_subscriber(self, camera_id: str, subscriber: WebSocketConnection) -> None:
        session = self._sessions.get(str(camera_id))
        if session is None or not session.running:
            raise RuntimeError(f"Camera {camera_id} is not running.")
        with session._stream_lock:
            session._stream_subscribers.add(subscriber)
            if session.latest_packet is not None:
                subscriber.send_json(session.latest_packet)

    def remove_stream_subscriber(self, camera_id: str, subscriber: WebSocketConnection) -> None:
        session = self._sessions.get(str(camera_id))
        if session is None:
            return
        with session._stream_lock:
            session._stream_subscribers.discard(subscriber)

    def add_event_subscriber(self, subscriber: WebSocketConnection) -> None:
        with self._event_lock:
            self._event_subscribers.add(subscriber)

    def remove_event_subscriber(self, subscriber: WebSocketConnection) -> None:
        with self._event_lock:
            self._event_subscribers.discard(subscriber)

    def _camera_loop(self, session: CameraSession) -> None:
        try:
            import cv2
        except Exception as exc:
            session.last_error = f"OpenCV unavailable: {exc}"
            session.running = False
            return

        source_value: Any = session.source
        if str(source_value).isdigit():
            source_value = int(str(source_value))

        capture = cv2.VideoCapture(source_value)
        if not capture.isOpened():
            session.last_error = f"Unable to open source: {session.source}"
            session.running = False
            capture.release()
            return

        last_frame_time = time.monotonic()
        last_analysis_time = 0.0
        try:
            while not session._stop.is_set():
                ok, frame = capture.read()
                if not ok or frame is None:
                    session.last_error = "Failed to read frame."
                    time.sleep(0.1)
                    continue

                now = time.monotonic()
                delta = max(1e-6, now - last_frame_time)
                last_frame_time = now
                session.frame_id += 1
                session.fps = round((session.fps * 0.8) + ((1.0 / delta) * 0.2), 2) if session.fps else round(1.0 / delta, 2)
                session.last_frame_at = datetime.now()

                if now - last_analysis_time >= 0.8:
                    session.latest_faces = self.adapter.analyze_frame(frame, session.camera_id, session.name_location)
                    self._persist_faces_if_needed(session)
                    self._broadcast_observation(session, frame.shape[1], frame.shape[0])
                    last_analysis_time = now

                ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if ok:
                    status = self.adapter.system_status(self.runtime_snapshot())
                    packet = FramePacket(
                        camera_id=session.camera_id,
                        slot_id=self._slot_id(session.camera_id),
                        frame_id=session.frame_id,
                        captured_at=datetime.now(),
                        source_uri=session.source,
                        width=int(frame.shape[1]),
                        height=int(frame.shape[0]),
                        color_space="bgr",
                        image_encoding="jpeg_base64",
                        image_data=base64.b64encode(encoded.tobytes()).decode("ascii"),
                        runtime_mode=status.runtime_mode,
                        backend_mode=status.backend_mode,
                    )
                    envelope = EventEnvelope(
                        event_type="camera.frame",
                        emitted_at=datetime.now(),
                        payload=packet,
                    )
                    session.latest_packet = envelope.model_dump(mode="json")
                    self._broadcast_stream(session, session.latest_packet)
                time.sleep(0.03)
        finally:
            capture.release()
            session.running = False

    def _broadcast_stream(self, session: CameraSession, payload: dict[str, Any]) -> None:
        with session._stream_lock:
            subscribers = list(session._stream_subscribers)
        dead: list[WebSocketConnection] = []
        for subscriber in subscribers:
            try:
                subscriber.send_json(payload)
            except WebSocketClosed:
                dead.append(subscriber)
            except Exception:
                dead.append(subscriber)
        if dead:
            with session._stream_lock:
                for subscriber in dead:
                    session._stream_subscribers.discard(subscriber)

    def _broadcast_observation(self, session: CameraSession, width: int, height: int) -> None:
        status = self.adapter.system_status(self.runtime_snapshot())
        frame = FramePacket(
            camera_id=session.camera_id,
            slot_id=self._slot_id(session.camera_id),
            frame_id=session.frame_id,
            captured_at=datetime.now(),
            source_uri=session.source,
            width=width,
            height=height,
            color_space="bgr",
            image_encoding="none",
            image_data=None,
            runtime_mode=status.runtime_mode,
            backend_mode=status.backend_mode,
        )
        detections: list[DetectionResult] = []
        recognitions: list[RecognitionResult] = []
        emotions: list[EmotionResult] = []
        alerts: list[AlertResult] = []
        for face in session.latest_faces:
            detections.append(
                DetectionResult(
                    camera_id=session.camera_id,
                    frame_id=session.frame_id,
                    track_id=face.track_id,
                    bbox=face.bbox,
                    det_score=face.det_score,
                    quality=face.quality,
                    detector="yolov8_face",
                    recognition_skipped=False,
                )
            )
            recognitions.append(
                RecognitionResult(
                    camera_id=session.camera_id,
                    frame_id=session.frame_id,
                    track_id=face.track_id,
                    bbox=face.bbox,
                    name=face.name or "unknown",
                    similarity=face.similarity,
                    confidence=face.confidence,
                    backend_mode=status.backend_mode,
                    match_reason=face.reason,
                )
            )
            if face.emotion is not None:
                emotions.append(
                    EmotionResult(
                        camera_id=session.camera_id,
                        frame_id=session.frame_id,
                        track_id=face.track_id,
                        name=face.name,
                        bbox=face.bbox,
                        emotion=face.emotion,
                        confidence=face.emotion_confidence if face.emotion_confidence is not None else 0.0,
                        quality="good" if face.emotion_confidence is not None else "fallback",
                        reason="model_vote" if face.emotion_confidence is not None else "fallback_neutral",
                    )
                )
            if face.name == "unknown":
                alerts.append(
                    AlertResult(
                        alert_id=f"unknown-{session.camera_id}-{session.frame_id}-{face.track_id}",
                        camera_id=session.camera_id,
                        frame_id=session.frame_id,
                        track_id=face.track_id,
                        alert_type="unknown_face",
                        severity="info",
                        status="open",
                        title="Unknown face",
                        message="A face was detected but not matched to the library.",
                        occurred_at=datetime.now(),
                        evidence={"bbox": face.bbox},
                    )
                )
        observation = VisionObservation(
            frame=frame,
            detections=detections,
            recognitions=recognitions,
            emotions=emotions,
            alerts=alerts,
            system_status=status,
        )
        payload = EventEnvelope(
            event_type="vision.observation",
            emitted_at=datetime.now(),
            payload=observation,
        ).model_dump(mode="json")
        session.latest_observation = payload
        with self._event_lock:
            subscribers = list(self._event_subscribers)
        dead: list[WebSocketConnection] = []
        for subscriber in subscribers:
            try:
                subscriber.send_json(payload)
            except WebSocketClosed:
                dead.append(subscriber)
            except Exception:
                dead.append(subscriber)
        if dead:
            with self._event_lock:
                for subscriber in dead:
                    self._event_subscribers.discard(subscriber)

    def _persist_faces_if_needed(self, session: CameraSession) -> None:
        now = time.monotonic()
        to_save: list[RuntimeFace] = []
        for face in session.latest_faces:
            if face.name == "unknown":
                continue
            last_seen = session._dedupe_cache.get(face.name, 0.0)
            if now - last_seen < self._persist_interval_seconds:
                continue
            session._dedupe_cache[face.name] = now
            to_save.append(face)
        if to_save:
            self.adapter.persist_recognition_faces(to_save, session.name_location)

    @staticmethod
    def _slot_id(camera_id: str) -> int | None:
        try:
            return int(str(camera_id))
        except ValueError:
            return None
