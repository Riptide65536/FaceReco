from __future__ import annotations

import base64
import threading
import time
import uuid
from datetime import datetime, time as datetime_time
from typing import Any

import numpy as np

from app.repositories import ConfigRepository, DataRepository, SqlRepository
from app.services.app_service import AppService

from backend_api.models import (
    AttendanceListResponse,
    AttendanceSummaryItem,
    CameraDescriptor,
    FaceDeleteResponse,
    FaceLibraryEntry,
    FaceLibraryResponse,
    FaceRegisterRequest,
    FaceRegisterResponse,
    LogListResponse,
    LogRecord,
    ModelTrainResponse,
    RuntimeFace,
    SystemStatus,
)


class LegacyAppAdapter:
    """Thin adapter around the existing desktop-oriented repositories/services."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._emotion_lock = threading.RLock()
        self._service = AppService()
        self._initialized = False
        self.config_repo: ConfigRepository = self._service.config_repo
        self.data_repo: DataRepository = self._service.data_repo
        self.sql_repo: SqlRepository = self._service.sql_repo

    @property
    def service(self) -> AppService:
        self._ensure_initialized()
        return self._service

    def _ensure_initialized(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self._service.initialize_state()
            self._initialized = True

    def authenticate(self, username: str, password: str) -> bool:
        self._ensure_initialized()
        self.sql_repo.refresh_connection()
        return bool(self.sql_repo.verify_login(str(username).strip(), password))

    def list_cameras(self, runtime_snapshot: dict[str, dict[str, Any]] | None = None) -> list[CameraDescriptor]:
        self._ensure_initialized()
        runtime_snapshot = runtime_snapshot or {}
        items: list[CameraDescriptor] = []
        status = self.system_status(runtime_snapshot)
        for slot in (1, 2, 3, 4):
            config_lines = self.config_repo.load_camera_slot(slot)
            name_location = config_lines[0] if len(config_lines) > 0 else ""
            display_mode = 0
            if len(config_lines) > 1:
                try:
                    display_mode = int(config_lines[1])
                except ValueError:
                    display_mode = 0
            source = config_lines[2] if len(config_lines) > 2 else ""
            snap = runtime_snapshot.get(str(slot), {})
            running = bool(snap.get("running", False))
            last_error = str(snap.get("last_error", "") or "")
            configured = bool(source != "")
            state = self._camera_state(configured=configured, running=running, last_error=last_error)
            items.append(
                CameraDescriptor(
                    camera_id=str(slot),
                    slot_id=slot,
                    display_name=name_location or f"Camera {slot}",
                    location=name_location or "",
                    source_uri=str(source),
                    state=state,
                    runtime_mode=status.runtime_mode,
                    backend_mode=status.backend_mode,
                    fps_overlay_enabled=status.fps_overlay_enabled,
                    model_pending=status.model_pending,
                    display_mode=display_mode,
                    configured=configured,
                    frame_id=int(snap.get("frame_id", 0)),
                    fps=float(snap.get("fps", 0.0)),
                    last_error=last_error,
                    started_at=snap.get("started_at"),
                    last_frame_at=snap.get("last_frame_at"),
                )
            )
        return items

    def save_camera_config(
        self,
        camera_id: str,
        source_uri: str,
        location: str,
        display_mode: int,
    ) -> CameraDescriptor:
        self._ensure_initialized()
        slot = self._coerce_slot(camera_id)
        self.config_repo.save_camera_slot(slot, location, display_mode, source_uri)
        return self.list_cameras({})[slot - 1]

    def system_status(self, runtime_snapshot: dict[str, dict[str, Any]] | None = None) -> SystemStatus:
        self._ensure_initialized()
        runtime_snapshot = runtime_snapshot or {}
        pipeline = self._service.pipeline
        emotion = getattr(pipeline, "emotion", None)
        configured = self.list_cameras_shallow(runtime_snapshot)
        backend_mode = self._normalize_backend_mode(pipeline.current_backend_mode())
        provider_chain = self._provider_chain(pipeline)
        recognition_error = pipeline.face_service_error_text() or pipeline.last_train_error_text() or None
        active_cameras = sum(1 for item in configured if item["running"])
        degraded = backend_mode in {"unavailable", "unknown"} or any(item["last_error"] for item in configured)
        if self.data_repo.is_model_pending():
            degraded = True
        return SystemStatus(
            runtime_mode=self._normalize_runtime_mode(self._service.state.realtime_mode),
            backend_mode=backend_mode,
            provider_chain=provider_chain,
            provider_display=pipeline.current_provider_display_text(),
            model_pending=self.data_repo.is_model_pending(),
            fps_overlay_enabled=bool(self._service.state.show_fps_overlay),
            active_cameras=active_cameras,
            registered_users=len(self._service.state.user_dic),
            degraded=degraded,
            legacy_mode_available=True,
            service="task-01-backend-api",
            version="0.2.0",
            time=datetime.now(),
            db_backend=str(getattr(self.sql_repo.db, "backend", "unknown")),
            recognition_error=recognition_error,
            emotion_model_format=str(getattr(emotion, "model_format", "missing")),
            emotion_runtime_device=str(getattr(emotion, "runtime_device", "CPU")),
            configured_cameras=sum(1 for item in configured if item["configured"]),
            system_lock_slot=int(self._service.state.system_lock_slot),
            custom_attendance_active=bool(self._service.state.custom_attendance_active),
            custom_attendance_label=self._service.state.custom_attendance_label or "",
        )

    def query_logs(
        self,
        *,
        name: str | None,
        location: str | None,
        start_time: datetime | None,
        end_time: datetime | None,
        attendance_type: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> LogListResponse:
        self._ensure_initialized()
        rows = self.sql_repo.query_logs_with_emotion(
            name=name,
            location=location,
            start_time=start_time,
            end_time=end_time,
            attendance_type=attendance_type,
            status=status,
        )
        total = len(rows)
        page = max(1, page)
        page_size = max(1, min(page_size, 200))
        start = (page - 1) * page_size
        sliced = rows[start : start + page_size]
        items = [self._row_to_log_record(row) for row in sliced]
        return LogListResponse(items=items, total=total, page=page, page_size=page_size)

    def query_attendance(
        self,
        *,
        name: str | None,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> AttendanceListResponse:
        self._ensure_initialized()
        if start_time is None:
            start_time = datetime.combine(datetime.now().date(), datetime_time.min)
        if end_time is None:
            end_time = datetime.combine(datetime.now().date(), datetime_time.max)
        rows = self.sql_repo.query_logs_with_emotion(
            name=name,
            location=None,
            start_time=start_time,
            end_time=end_time,
            attendance_type=None,
            status=None,
        )
        items = [self._row_to_log_record(row) for row in rows]
        summary = self.sql_repo.get_attendance_summary(start_time, end_time)
        summary_items: list[AttendanceSummaryItem] = []
        for person_name, counts in sorted(summary.items(), key=lambda item: item[0]):
            if name and person_name != name:
                continue
            summary_items.append(AttendanceSummaryItem(name=person_name, counts=dict(counts)))
        return AttendanceListResponse(items=items, summary=summary_items)

    def list_faces(self) -> FaceLibraryResponse:
        self._ensure_initialized()
        entries: list[FaceLibraryEntry] = []
        model_pending = self.data_repo.is_model_pending()
        for user_id, username in sorted(self._service.state.user_dic.items(), key=lambda item: int(item[0])):
            resolved = self.data_repo.resolve_user_dir(int(user_id), username)
            directory = resolved or self.data_repo.user_dir_path(username)
            sample_count = 0
            if directory.exists():
                sample_count = sum(1 for path in directory.iterdir() if path.is_file())
            entries.append(
                FaceLibraryEntry(
                    user_id=int(user_id),
                    name=str(username),
                    sample_count=sample_count,
                    directory=str(directory),
                    model_pending=model_pending,
                )
            )
        return FaceLibraryResponse(items=entries, total=len(entries), model_pending=model_pending)

    def register_faces(self, payload: FaceRegisterRequest) -> FaceRegisterResponse:
        self._ensure_initialized()
        if payload.mode == "from_camera":
            raise ValueError("mode=from_camera is reserved for later runtime integration and is not available yet.")
        if not payload.images:
            raise ValueError("Upload mode requires at least one base64 image.")
        with self._lock:
            username = str(payload.name or "").strip()
            if not username:
                raise ValueError("name is required.")
            if payload.replace_existing:
                target_dir = self.data_repo.recreate_user_dir(username)
            else:
                target_dir = self.data_repo.user_dir_path(username)
                target_dir.mkdir(parents=True, exist_ok=True)

            user_id = self._service.ensure_user_registered(username)
            saved = 0
            for idx, image_payload in enumerate(payload.images, start=1):
                image = self._decode_image(image_payload.content_base64)
                target = target_dir / f"{int(time.time() * 1000)}_{idx}_{image_payload.filename or 'face'}.jpg"
                if self.data_repo.write_face_image(target, image):
                    saved += 1

            self._service.persist_training_state()
            rebuild_success: bool | None = None
            if payload.auto_train:
                rebuild_success = self._service.rebuild_and_train()
            else:
                self._service.mark_model_pending()
                self._service.persist_training_state()

            self.sql_repo.save_model_metadata(username, str(target_dir), label=user_id)
            return FaceRegisterResponse(
                ok=saved > 0,
                name=username,
                enrollment_session_id=f"upload-{uuid.uuid4().hex[:12]}",
                sample_count_target=payload.sample_count_target,
                model_pending=self.data_repo.is_model_pending(),
                message="registered" if saved > 0 else "no image saved",
                user_id=user_id,
                saved_images=saved,
                rebuild_success=rebuild_success,
            )

    def delete_face(self, username: str, retrain: bool) -> FaceDeleteResponse:
        self._ensure_initialized()
        with self._lock:
            cleaned = username.strip()
            existing = {item.name for item in self.list_faces().items}
            if cleaned not in existing:
                return FaceDeleteResponse(
                    ok=False,
                    name=cleaned,
                    retrained=False,
                    model_pending=self.data_repo.is_model_pending(),
                    message="user not found",
                )
            if retrain:
                ok = self._service.delete_user_and_rebuild(cleaned)
                return FaceDeleteResponse(
                    ok=ok,
                    name=cleaned,
                    retrained=ok,
                    model_pending=self.data_repo.is_model_pending(),
                    message="deleted and retrained" if ok else "delete failed",
                )
            ok = self._service.delete_user_only(cleaned)
            return FaceDeleteResponse(
                ok=ok,
                name=cleaned,
                retrained=False,
                model_pending=self.data_repo.is_model_pending(),
                message="deleted" if ok else "delete failed",
            )

    def train_model(self) -> ModelTrainResponse:
        self._ensure_initialized()
        ok = self._service.rebuild_and_train()
        return ModelTrainResponse(
            ok=ok,
            backend_mode=self._normalize_backend_mode(self._service.pipeline.current_backend_mode()),
            model_pending=self.data_repo.is_model_pending(),
            sample_count=len(self._service.state.face_samples),
            user_count=len(self._service.state.user_dic),
            detail=None if ok else (self._service.pipeline.last_train_error_text() or "train failed"),
        )

    def analyze_frame(self, frame: np.ndarray, camera_id: str, location: str) -> list[RuntimeFace]:
        self._ensure_initialized()
        pipeline = self._service.pipeline
        if pipeline.face_service is None:
            return []
        gray = frame if len(frame.shape) == 2 else pipeline.face_service.to_gray(frame)
        predictions = pipeline.face_service.recognize_frame(gray)
        results: list[RuntimeFace] = []
        for idx, pred in enumerate(predictions, start=1):
            x, y, w, h = [int(v) for v in pred.get("bbox", (0, 0, 0, 0))]
            emotion = None
            emotion_confidence = None
            if w > 0 and h > 0 and pipeline.emotion is not None:
                try:
                    crop = gray[y : y + h, x : x + w]
                    if crop.size > 0:
                        with self._emotion_lock:
                            emotion, emotion_confidence = pipeline.emotion.predict(crop)
                except Exception:
                    emotion = None
                    emotion_confidence = None
            name = str(pred.get("name") or "unknown")
            confidence = pred.get("confidence")
            similarity = pred.get("similarity")
            reason = str(pred.get("match_reason") or ("fallback" if name == "unknown" else "fresh"))
            results.append(
                RuntimeFace(
                    track_id=idx,
                    bbox=[x, y, w, h],
                    det_score=float(pred.get("det_score")) if pred.get("det_score") is not None else None,
                    quality=self._face_quality(w, h),
                    name=name,
                    similarity=float(similarity) if similarity is not None else None,
                    confidence=float(confidence) if confidence is not None else None,
                    reason=reason,
                    emotion=emotion,
                    emotion_confidence=float(emotion_confidence) if emotion_confidence is not None else None,
                )
            )
        return results

    def persist_recognition_faces(self, faces: list[RuntimeFace], location: str) -> int:
        self._ensure_initialized()
        saved = 0
        for face in faces:
            if face.name == "unknown":
                continue
            ok = self.sql_repo.save_recognition_event(
                name=face.name,
                location=location,
                timepoint=datetime.now(),
                emotion=face.emotion or "neutral",
            )
            if ok:
                saved += 1
        return saved

    def list_cameras_shallow(self, runtime_snapshot: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for slot in (1, 2, 3, 4):
            config_lines = self.config_repo.load_camera_slot(slot)
            source = config_lines[2] if len(config_lines) > 2 else ""
            snap = runtime_snapshot.get(str(slot), {})
            items.append(
                {
                    "configured": bool(source != ""),
                    "running": bool(snap.get("running", False)),
                    "last_error": str(snap.get("last_error", "") or ""),
                }
            )
        return items

    @staticmethod
    def _camera_state(*, configured: bool, running: bool, last_error: str) -> str:
        if last_error:
            return "error"
        if running:
            return "running"
        if configured:
            return "stopped"
        return "offline"

    @staticmethod
    def _normalize_runtime_mode(value: str) -> str:
        cleaned = str(value or "balanced").strip().lower()
        if cleaned in {"realtime", "balanced", "accurate"}:
            return cleaned
        return "balanced"

    @staticmethod
    def _normalize_backend_mode(value: str) -> str:
        cleaned = str(value or "unknown").strip().lower()
        if cleaned in {"deep", "lbph", "lite", "unavailable", "unknown"}:
            return cleaned
        return "unknown"

    @staticmethod
    def _provider_chain(pipeline: Any) -> list[str]:
        face_service = getattr(pipeline, "face_service", None)
        providers = getattr(face_service, "_deep_providers", None) if face_service is not None else None
        if not providers:
            return []
        return [str(item) for item in providers]

    @staticmethod
    def _row_to_log_record(row: Any) -> LogRecord:
        return LogRecord(
            name=str(row[0] or ""),
            location=str(row[1] or ""),
            timestamp=LegacyAppAdapter._coerce_datetime(row[2]),
            emotion=str(row[3] or "neutral"),
            attendance_type=str(row[4] or ""),
            status=str(row[5] or ""),
            image_path=row[6] if len(row) > 6 else None,
        )

    @staticmethod
    def _face_quality(width: int, height: int) -> str:
        area = int(width) * int(height)
        if area >= 12_000:
            return "good"
        if area >= 4_000:
            return "weak"
        return "bad"

    @staticmethod
    def _decode_image(content_base64: str) -> np.ndarray:
        try:
            import cv2
        except Exception as exc:
            raise RuntimeError("OpenCV is required for face registration.") from exc
        raw = base64.b64decode(content_base64)
        array = np.frombuffer(raw, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Invalid image payload.")
        return image

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            text = value.split(".")[0]
            try:
                return datetime.fromisoformat(text)
            except ValueError:
                return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        raise TypeError(f"Unsupported datetime value: {value!r}")

    @staticmethod
    def _coerce_slot(camera_id: str) -> int:
        try:
            slot = int(str(camera_id).strip())
        except ValueError as exc:
            raise ValueError("camera_id must be an integer string between 1 and 4.") from exc
        if slot not in {1, 2, 3, 4}:
            raise ValueError("camera_id must be between 1 and 4.")
        return slot
