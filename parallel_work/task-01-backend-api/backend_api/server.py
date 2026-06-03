from __future__ import annotations

import atexit
import json
import threading
import urllib.parse
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from pydantic import ValidationError

from backend_api.adapters.legacy_app import LegacyAppAdapter
from backend_api.core.auth import TokenStore
from backend_api.core.websocket import WebSocketConnection, build_accept_value
from backend_api.models import (
    CameraControlResponse,
    CameraListResponse,
    CameraStartRequest,
    CameraStopRequest,
    ErrorResponse,
    FaceRegisterRequest,
    HealthResponse,
    LoginRequest,
    LoginResponse,
)
from backend_api.openapi import build_openapi
from backend_api.runtime.camera_manager import CameraManager


class BackendApplication:
    def __init__(self) -> None:
        self.adapter = LegacyAppAdapter()
        self.tokens = TokenStore()
        self.cameras = CameraManager(self.adapter)
        self.openapi = build_openapi()

    def shutdown(self) -> None:
        self.cameras.shutdown()


class BackendServer:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = int(port)
        self.app = BackendApplication()
        handler = self._build_handler()
        self.httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self.httpd.daemon_threads = True
        atexit.register(self.app.shutdown)

    def serve_forever(self) -> None:
        self.httpd.serve_forever(poll_interval=0.5)

    def shutdown(self) -> None:
        self.app.shutdown()
        self.httpd.shutdown()
        self.httpd.server_close()

    def _build_handler(self):
        app = self.app

        class RequestHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "Task01Backend/0.1"

            def do_OPTIONS(self) -> None:
                self.send_response(HTTPStatus.NO_CONTENT)
                self._send_cors_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
                if path == "/api/health":
                    return self._send_json(
                        HTTPStatus.OK,
                        HealthResponse(
                            status="ok",
                            service="task-01-backend-api",
                            version="0.2.0",
                            time=datetime.now(),
                        ),
                    )
                if path == "/openapi.json":
                    return self._send_json(HTTPStatus.OK, app.openapi)
                if path.startswith("/ws/"):
                    return self._handle_websocket(path, query)
                session = self._require_auth(query=query)
                if session is None:
                    return
                if path == "/api/system/status":
                    return self._send_json(HTTPStatus.OK, app.adapter.system_status(app.cameras.runtime_snapshot()))
                if path == "/api/cameras":
                    return self._send_json(
                        HTTPStatus.OK,
                        CameraListResponse(items=app.adapter.list_cameras(app.cameras.runtime_snapshot())),
                    )
                if path == "/api/logs":
                    return self._handle_logs(query)
                if path == "/api/attendance":
                    return self._handle_attendance(query)
                if path == "/api/faces":
                    return self._send_json(HTTPStatus.OK, app.adapter.list_faces())
                self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", "Endpoint not found.")

            def do_POST(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
                if path == "/api/auth/login":
                    return self._handle_login()
                session = self._require_auth(query=query)
                if session is None:
                    return
                if path == "/api/cameras/start":
                    return self._handle_camera_start()
                if path == "/api/cameras/stop":
                    return self._handle_camera_stop()
                if path == "/api/faces/register":
                    return self._handle_face_register()
                if path == "/api/models/train":
                    return self._send_json(HTTPStatus.OK, app.adapter.train_model())
                self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", "Endpoint not found.")

            def do_DELETE(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
                session = self._require_auth(query=query)
                if session is None:
                    return
                if path.startswith("/api/faces/"):
                    username = urllib.parse.unquote(path.split("/api/faces/", 1)[1])
                    retrain = self._query_bool(query, "retrain", default=self._query_bool(query, "rebuild_model", default=False))
                    response = app.adapter.delete_face(username, retrain=retrain)
                    return self._send_json(HTTPStatus.OK, response)
                self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", "Endpoint not found.")

            def _handle_login(self) -> None:
                payload = self._read_model(LoginRequest)
                if payload is None:
                    return
                if not app.adapter.authenticate(payload.username, payload.password):
                    self._send_error_json(HTTPStatus.UNAUTHORIZED, "auth_failed", "Invalid username or password.")
                    return
                session = app.tokens.issue(payload.username)
                response = LoginResponse(
                    ok=True,
                    token=session.token,
                    access_token=session.token,
                    expires_at=session.expires_at,
                    username=session.username,
                )
                self._send_json(HTTPStatus.OK, response)

            def _handle_camera_start(self) -> None:
                payload = self._read_model(CameraStartRequest)
                if payload is None:
                    return
                cameras = {item.camera_id: item for item in app.adapter.list_cameras(app.cameras.runtime_snapshot())}
                current = cameras.get(payload.camera_id)
                if current is None:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid_camera", "camera_id must be between 1 and 4.")
                    return
                source = payload.source_uri if payload.source_uri is not None else current.source_uri
                name_location = payload.location if payload.location is not None else (current.location or "")
                display_mode = payload.display_mode if payload.display_mode is not None else current.display_mode
                if source in (None, ""):
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "missing_source", "Camera source is required.")
                    return
                app.adapter.save_camera_config(payload.camera_id, str(source), str(name_location or ""), int(display_mode or 0))
                try:
                    app.cameras.start_camera(payload.camera_id, str(source), str(name_location or ""), int(display_mode or 0))
                except Exception as exc:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "camera_start_failed", str(exc))
                    return
                camera = {item.camera_id: item for item in app.adapter.list_cameras(app.cameras.runtime_snapshot())}[payload.camera_id]
                self._send_json(HTTPStatus.OK, CameraControlResponse(ok=True, camera=camera, message="camera started"))

            def _handle_camera_stop(self) -> None:
                payload = self._read_model(CameraStopRequest)
                if payload is None:
                    return
                stopped = app.cameras.stop_camera(payload.camera_id)
                cameras = {item.camera_id: item for item in app.adapter.list_cameras(app.cameras.runtime_snapshot())}
                camera = cameras.get(payload.camera_id)
                if camera is None:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid_camera", "camera_id must be between 1 and 4.")
                    return
                response = CameraControlResponse(
                    ok=stopped,
                    camera=camera,
                    message="camera stopped" if stopped else "camera not running",
                )
                self._send_json(HTTPStatus.OK, response)

            def _handle_logs(self, query: dict[str, list[str]]) -> None:
                page = int(self._query_single(query, "page", "1"))
                page_size = int(self._query_single(query, "page_size", "20"))
                response = app.adapter.query_logs(
                    name=self._none_if_empty(self._query_single(query, "name")),
                    location=self._none_if_empty(self._query_single(query, "location")),
                    start_time=self._query_datetime(query, "start_time"),
                    end_time=self._query_datetime(query, "end_time"),
                    attendance_type=self._none_if_empty(self._query_single(query, "attendance_type")),
                    status=self._none_if_empty(self._query_single(query, "status")),
                    page=page,
                    page_size=page_size,
                )
                self._send_json(HTTPStatus.OK, response)

            def _handle_attendance(self, query: dict[str, list[str]]) -> None:
                start_time = self._query_datetime(query, "start_time")
                end_time = self._query_datetime(query, "end_time")
                response = app.adapter.query_attendance(
                    name=self._none_if_empty(self._query_single(query, "name")),
                    start_time=start_time,
                    end_time=end_time,
                )
                self._send_json(HTTPStatus.OK, response)

            def _handle_face_register(self) -> None:
                payload = self._read_model(FaceRegisterRequest)
                if payload is None:
                    return
                try:
                    response = app.adapter.register_faces(payload)
                except Exception as exc:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "register_failed", str(exc))
                    return
                self._send_json(HTTPStatus.OK, response)

            def _handle_websocket(self, path: str, query: dict[str, list[str]]) -> None:
                token = self._query_single(query, "token")
                if app.tokens.validate(token) is None:
                    self._send_error_json(HTTPStatus.UNAUTHORIZED, "auth_required", "Valid token is required for websocket.")
                    return
                key = self.headers.get("Sec-WebSocket-Key", "").strip()
                upgrade = self.headers.get("Upgrade", "").lower()
                if not key or upgrade != "websocket":
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "bad_websocket_request", "Missing websocket headers.")
                    return

                self.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", build_accept_value(key))
                self.end_headers()

                connection = WebSocketConnection(self.connection, self.rfile, self.wfile)
                if path == "/ws/events":
                    app.cameras.add_event_subscriber(connection)
                    try:
                        connection.wait_until_closed()
                    finally:
                        app.cameras.remove_event_subscriber(connection)
                    return
                if path.startswith("/ws/stream/"):
                    camera_id = path.split("/ws/stream/", 1)[1]
                    try:
                        app.cameras.add_stream_subscriber(camera_id, connection)
                    except Exception as exc:
                        connection.send_json({"error": "camera_not_running", "detail": str(exc)})
                        connection.close()
                        return
                    try:
                        connection.wait_until_closed()
                    finally:
                        app.cameras.remove_stream_subscriber(camera_id, connection)
                    return
                connection.send_json({"error": "not_found"})
                connection.close()

            def _require_auth(self, *, query: dict[str, list[str]] | None = None):
                token = None
                auth_header = self.headers.get("Authorization", "")
                if auth_header.lower().startswith("bearer "):
                    token = auth_header.split(" ", 1)[1].strip()
                if token is None and query is not None:
                    token = self._query_single(query, "token")
                session = app.tokens.validate(token)
                if session is None:
                    self._send_error_json(HTTPStatus.UNAUTHORIZED, "auth_required", "Bearer token required.")
                    return None
                return session

            def _read_model(self, model_cls):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                    return model_cls.model_validate(payload)
                except json.JSONDecodeError as exc:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid_json", str(exc))
                    return None
                except ValidationError as exc:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "validation_error", exc.json())
                    return None

            def _send_json(self, status: HTTPStatus, payload: Any) -> None:
                if hasattr(payload, "model_dump"):
                    body = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
                else:
                    body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
                self.send_response(status)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_error_json(self, status: HTTPStatus, error: str, detail: str) -> None:
                self._send_json(status, ErrorResponse(error=error, detail=detail))

            def _send_cors_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")

            @staticmethod
            def _query_single(query: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
                values = query.get(key)
                if not values:
                    return default
                return values[0]

            @staticmethod
            def _query_bool(query: dict[str, list[str]], key: str, default: bool = False) -> bool:
                value = RequestHandler._query_single(query, key)
                if value is None:
                    return default
                return str(value).strip().lower() in {"1", "true", "yes", "on"}

            @staticmethod
            def _query_datetime(query: dict[str, list[str]], key: str) -> datetime | None:
                value = RequestHandler._query_single(query, key)
                if value in (None, ""):
                    return None
                return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

            @staticmethod
            def _none_if_empty(value: str | None) -> str | None:
                if value is None:
                    return None
                cleaned = str(value).strip()
                return cleaned or None

            def log_message(self, format: str, *args) -> None:
                return

        return RequestHandler


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
