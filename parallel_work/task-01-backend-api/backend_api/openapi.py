from __future__ import annotations

from backend_api.models import (
    AttendanceListResponse,
    CameraControlResponse,
    CameraListResponse,
    CameraStartRequest,
    CameraStopRequest,
    ErrorResponse,
    EventEnvelope,
    FaceDeleteResponse,
    FaceLibraryResponse,
    FaceRegisterRequest,
    FaceRegisterResponse,
    HealthResponse,
    LoginRequest,
    LoginResponse,
    LogListResponse,
    ModelTrainResponse,
    SystemStatus,
)


def _schema(model) -> dict:
    return model.model_json_schema(ref_template="#/components/schemas/{model}")


def build_openapi() -> dict:
    schemas = {
        "HealthResponse": _schema(HealthResponse),
        "ErrorResponse": _schema(ErrorResponse),
        "LoginRequest": _schema(LoginRequest),
        "LoginResponse": _schema(LoginResponse),
        "SystemStatus": _schema(SystemStatus),
        "CameraListResponse": _schema(CameraListResponse),
        "CameraStartRequest": _schema(CameraStartRequest),
        "CameraStopRequest": _schema(CameraStopRequest),
        "CameraControlResponse": _schema(CameraControlResponse),
        "LogListResponse": _schema(LogListResponse),
        "AttendanceListResponse": _schema(AttendanceListResponse),
        "FaceLibraryResponse": _schema(FaceLibraryResponse),
        "FaceRegisterRequest": _schema(FaceRegisterRequest),
        "FaceRegisterResponse": _schema(FaceRegisterResponse),
        "FaceDeleteResponse": _schema(FaceDeleteResponse),
        "ModelTrainResponse": _schema(ModelTrainResponse),
        "EventEnvelope": _schema(EventEnvelope),
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Task-01 Backend API",
            "version": "0.2.0",
            "summary": "Backend API adapter for the parallel facial recognition migration.",
            "description": (
                "Standalone backend API built in parallel_work/task-01-backend-api. "
                "It wraps the existing Python recognition and data layer and aligns its public "
                "REST/WebSocket shape with parallel_work/task-00-contracts."
            ),
        },
        "servers": [{"url": "http://127.0.0.1:18080"}],
        "tags": [
            {"name": "auth"},
            {"name": "system"},
            {"name": "cameras"},
            {"name": "logs"},
            {"name": "attendance"},
            {"name": "faces"},
            {"name": "models"},
        ],
        "components": {
            "schemas": schemas,
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "opaque-token",
                }
            },
        },
        "paths": {
            "/api/health": {
                "get": {
                    "tags": ["system"],
                    "summary": "Health check",
                    "operationId": "healthCheck",
                    "responses": {"200": _json_response("OK", "HealthResponse")},
                }
            },
            "/api/auth/login": {
                "post": {
                    "tags": ["auth"],
                    "summary": "Validate user credentials",
                    "operationId": "login",
                    "requestBody": _request_body("LoginRequest"),
                    "responses": {
                        "200": _json_response("Login succeeded", "LoginResponse"),
                        "401": _json_response("Invalid credentials", "ErrorResponse"),
                    },
                }
            },
            "/api/system/status": {
                "get": {
                    "tags": ["system"],
                    "summary": "Return current backend, runtime, and model status",
                    "operationId": "getSystemStatus",
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": _json_response("Current system status", "SystemStatus")},
                }
            },
            "/api/cameras": {
                "get": {
                    "tags": ["cameras"],
                    "summary": "List camera configs and runtime state",
                    "operationId": "listCameras",
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": _json_response("Camera list", "CameraListResponse")},
                }
            },
            "/api/cameras/start": {
                "post": {
                    "tags": ["cameras"],
                    "summary": "Start or restart a camera source",
                    "operationId": "startCamera",
                    "security": [{"BearerAuth": []}],
                    "requestBody": _request_body("CameraStartRequest"),
                    "responses": {
                        "200": _json_response("Camera accepted for startup", "CameraControlResponse"),
                        "409": _json_response("Camera source conflict", "ErrorResponse"),
                    },
                }
            },
            "/api/cameras/stop": {
                "post": {
                    "tags": ["cameras"],
                    "summary": "Stop a running camera source",
                    "operationId": "stopCamera",
                    "security": [{"BearerAuth": []}],
                    "requestBody": _request_body("CameraStopRequest"),
                    "responses": {"200": _json_response("Camera stopped", "CameraControlResponse")},
                }
            },
            "/api/logs": {
                "get": {
                    "tags": ["logs"],
                    "summary": "Query recognition logs with emotion and attendance fields",
                    "operationId": "queryLogs",
                    "security": [{"BearerAuth": []}],
                    "parameters": _common_log_params(include_page=True),
                    "responses": {"200": _json_response("Log list", "LogListResponse")},
                }
            },
            "/api/attendance": {
                "get": {
                    "tags": ["attendance"],
                    "summary": "Query attendance-facing records and summary inputs",
                    "operationId": "queryAttendance",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {"name": "name", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "start_time", "in": "query", "required": False, "schema": {"type": "string", "format": "date-time"}},
                        {"name": "end_time", "in": "query", "required": False, "schema": {"type": "string", "format": "date-time"}},
                    ],
                    "responses": {"200": _json_response("Attendance records and summary", "AttendanceListResponse")},
                }
            },
            "/api/faces": {
                "get": {
                    "tags": ["faces"],
                    "summary": "List face library users and sample counts",
                    "operationId": "listFaces",
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": _json_response("Face list", "FaceLibraryResponse")},
                }
            },
            "/api/faces/register": {
                "post": {
                    "tags": ["faces"],
                    "summary": "Register uploaded face samples",
                    "operationId": "registerFace",
                    "security": [{"BearerAuth": []}],
                    "requestBody": _request_body("FaceRegisterRequest"),
                    "responses": {
                        "200": _json_response("Enrollment request accepted", "FaceRegisterResponse"),
                        "400": _json_response("Invalid request", "ErrorResponse"),
                    },
                }
            },
            "/api/faces/{name}": {
                "delete": {
                    "tags": ["faces"],
                    "summary": "Delete a user and optionally retrain immediately",
                    "operationId": "deleteFace",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {"name": "name", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "retrain", "in": "query", "required": False, "schema": {"type": "boolean", "default": False}},
                    ],
                    "responses": {"200": _json_response("Deletion completed", "FaceDeleteResponse")},
                }
            },
            "/api/models/train": {
                "post": {
                    "tags": ["models"],
                    "summary": "Rebuild training data and train current face model",
                    "operationId": "trainModel",
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": _json_response("Train request finished", "ModelTrainResponse")},
                }
            },
            "/ws/stream/{camera_id}": {
                "get": {
                    "summary": "WebSocket camera frame stream",
                    "security": [{"BearerAuth": []}],
                    "description": "Connect with ?token=... and receive EventEnvelope messages with event_type=camera.frame.",
                    "responses": {"101": {"description": "Switching Protocols"}},
                }
            },
            "/ws/events": {
                "get": {
                    "summary": "WebSocket system-wide event stream",
                    "security": [{"BearerAuth": []}],
                    "description": "Connect with ?token=... and receive EventEnvelope messages such as vision.observation.",
                    "responses": {"101": {"description": "Switching Protocols"}},
                }
            },
        },
        "x-websocket-channels": {
            "/ws/stream/{camera_id}": {
                "summary": "Camera stream channel",
                "server_messages": [{"schema": {"$ref": "#/components/schemas/EventEnvelope"}}],
            },
            "/ws/events": {
                "summary": "System-wide event channel",
                "server_messages": [{"schema": {"$ref": "#/components/schemas/EventEnvelope"}}],
            },
        },
    }


def _json_response(description: str, schema_name: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}},
    }


def _request_body(schema_name: str) -> dict:
    return {
        "required": True,
        "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}},
    }


def _common_log_params(include_page: bool) -> list[dict]:
    params = [
        {"name": "name", "in": "query", "required": False, "schema": {"type": "string"}},
        {"name": "location", "in": "query", "required": False, "schema": {"type": "string"}},
        {"name": "start_time", "in": "query", "required": False, "schema": {"type": "string", "format": "date-time"}},
        {"name": "end_time", "in": "query", "required": False, "schema": {"type": "string", "format": "date-time"}},
        {"name": "attendance_type", "in": "query", "required": False, "schema": {"type": "string"}},
        {"name": "status", "in": "query", "required": False, "schema": {"type": "string"}},
    ]
    if include_page:
        params.extend(
            [
                {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}},
                {"name": "page_size", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20}},
            ]
        )
    return params
