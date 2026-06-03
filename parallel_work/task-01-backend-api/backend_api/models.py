from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RuntimeMode = Literal["realtime", "balanced", "accurate"]
BackendMode = Literal["deep", "lbph", "lite", "unavailable", "unknown"]
CameraState = Literal["starting", "running", "stopping", "stopped", "error", "offline"]
EventType = Literal["camera.frame", "camera.state", "system.status", "vision.observation", "alert.raised"]
Quality = Literal["good", "weak", "bad"]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["open", "acknowledged", "resolved"]


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    time: datetime


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    ok: bool = True
    username: str
    role: str | None = "admin"
    token: str
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: datetime


class CameraDescriptor(BaseModel):
    camera_id: str
    slot_id: int | None = None
    display_name: str | None = None
    location: str | None = None
    source_uri: str
    state: CameraState
    runtime_mode: RuntimeMode
    backend_mode: BackendMode
    fps_overlay_enabled: bool
    model_pending: bool
    display_mode: int = 0
    configured: bool = False
    frame_id: int = 0
    fps: float = 0.0
    last_error: str = ""
    started_at: datetime | None = None
    last_frame_at: datetime | None = None


class CameraListResponse(BaseModel):
    items: list[CameraDescriptor]


class CameraStartRequest(BaseModel):
    camera_id: str
    slot_id: int | None = None
    display_name: str | None = None
    location: str | None = None
    source_uri: str | None = None
    source: str | None = None
    display_mode: int = Field(default=0, ge=0, le=10)
    runtime_mode: RuntimeMode | None = None

    @model_validator(mode="after")
    def _normalize(self) -> "CameraStartRequest":
        if self.source_uri is None and self.source is not None:
            self.source_uri = self.source
        if self.location is None and self.display_name is not None:
            self.location = self.display_name
        return self


class CameraStopRequest(BaseModel):
    camera_id: str


class CameraControlResponse(BaseModel):
    ok: bool
    message: str | None = None
    camera: CameraDescriptor


class LogRecord(BaseModel):
    name: str
    location: str
    timestamp: datetime
    emotion: str
    attendance_type: str
    status: str
    image_path: str | None = None


class LogListResponse(BaseModel):
    items: list[LogRecord]
    total: int | None = None
    page: int | None = None
    page_size: int | None = None


class AttendanceSummaryItem(BaseModel):
    name: str
    counts: dict[str, int]


class AttendanceListResponse(BaseModel):
    items: list[LogRecord]
    summary: list[AttendanceSummaryItem]


class FaceLibraryEntry(BaseModel):
    user_id: int
    name: str
    sample_count: int
    directory: str
    model_pending: bool


class FaceLibraryResponse(BaseModel):
    items: list[FaceLibraryEntry]
    total: int
    model_pending: bool


class FaceImagePayload(BaseModel):
    filename: str
    content_base64: str


class FaceRegisterRequest(BaseModel):
    name: str | None = None
    username: str | None = None
    mode: Literal["from_camera", "upload"] = "upload"
    camera_id: str | None = None
    sample_count_target: int = Field(default=20, ge=1, le=200)
    auto_train: bool = False
    images: list[FaceImagePayload] = Field(default_factory=list)
    replace_existing: bool = False

    @model_validator(mode="after")
    def _normalize(self) -> "FaceRegisterRequest":
        if self.name is None and self.username is not None:
            self.name = self.username
        return self


class FaceRegisterResponse(BaseModel):
    ok: bool
    name: str
    enrollment_session_id: str | None = None
    sample_count_target: int | None = None
    model_pending: bool
    message: str | None = None
    user_id: int | None = None
    saved_images: int | None = None
    rebuild_success: bool | None = None


class FaceDeleteResponse(BaseModel):
    ok: bool
    name: str
    retrained: bool
    model_pending: bool
    message: str | None = None


class ModelTrainResponse(BaseModel):
    ok: bool
    backend_mode: BackendMode
    model_pending: bool
    sample_count: int | None = None
    user_count: int | None = None
    detail: str | None = None


class SystemStatus(BaseModel):
    runtime_mode: RuntimeMode
    backend_mode: BackendMode
    provider_chain: list[str] = Field(default_factory=list)
    provider_display: str | None = None
    model_pending: bool
    fps_overlay_enabled: bool
    active_cameras: int
    registered_users: int
    degraded: bool
    legacy_mode_available: bool = True
    service: str | None = None
    version: str | None = None
    time: datetime | None = None
    db_backend: str | None = None
    recognition_error: str | None = None
    emotion_model_format: str | None = None
    emotion_runtime_device: str | None = None
    configured_cameras: int | None = None
    system_lock_slot: int | None = None
    custom_attendance_active: bool | None = None
    custom_attendance_label: str | None = None


class FramePacket(BaseModel):
    camera_id: str
    slot_id: int | None = None
    frame_id: int
    captured_at: datetime
    source_uri: str
    width: int
    height: int
    color_space: Literal["bgr", "rgb", "gray"] = "bgr"
    image_encoding: Literal["jpeg_base64", "png_base64", "none"] | None = "jpeg_base64"
    image_data: str | None = None
    runtime_mode: RuntimeMode
    backend_mode: BackendMode


class DetectionResult(BaseModel):
    camera_id: str
    frame_id: int
    track_id: int | None = None
    bbox: list[int] = Field(min_length=4, max_length=4)
    det_score: float | None = None
    quality: Quality
    detector: str
    recognition_skipped: bool | None = None


class RecognitionResult(BaseModel):
    camera_id: str
    frame_id: int
    track_id: int | None = None
    bbox: list[int] = Field(min_length=4, max_length=4)
    label_id: int | None = None
    name: str
    similarity: float | None = None
    confidence: float | None = None
    backend_mode: BackendMode
    match_reason: str | None = None


class EmotionResult(BaseModel):
    camera_id: str
    frame_id: int
    track_id: int | None = None
    name: str | None = None
    bbox: list[int] | None = Field(default=None, min_length=4, max_length=4)
    emotion: str
    confidence: float
    quality: Literal["good", "weak", "bad", "fallback"]
    reason: str


class AlertResult(BaseModel):
    alert_id: str
    camera_id: str | None = None
    frame_id: int | None = None
    track_id: int | None = None
    alert_type: Literal[
        "unknown_face",
        "camera_offline",
        "backend_degraded",
        "model_pending",
        "attendance_absence",
        "stream_error",
    ]
    severity: AlertSeverity
    status: AlertStatus
    title: str
    message: str
    occurred_at: datetime
    evidence: dict[str, Any] | None = None


class VisionObservation(BaseModel):
    frame: FramePacket
    detections: list[DetectionResult]
    recognitions: list[RecognitionResult]
    emotions: list[EmotionResult]
    alerts: list[AlertResult]
    system_status: SystemStatus


class CameraStatePayload(BaseModel):
    camera_id: str
    state: CameraState
    message: str | None = None


class EventEnvelope(BaseModel):
    event_type: EventType
    event_version: Literal["v1"] = "v1"
    emitted_at: datetime
    payload: FramePacket | CameraStatePayload | SystemStatus | VisionObservation | AlertResult


class RuntimeFace(BaseModel):
    track_id: int
    bbox: list[int]
    det_score: float | None = None
    quality: Quality = "good"
    name: str
    similarity: float | None = None
    confidence: float | None = None
    reason: str = "fresh"
    emotion: str | None = None
    emotion_confidence: float | None = None
    model_config = ConfigDict(arbitrary_types_allowed=True)
