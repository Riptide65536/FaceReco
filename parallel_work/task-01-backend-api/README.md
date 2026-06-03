# Task-01 Backend API

This directory contains the standalone backend API slice for the parallel migration. It is intentionally kept inside `parallel_work/task-01-backend-api/` and only reads the legacy project modules as an adapter source.

The current implementation uses Python's standard HTTP server plus Pydantic models and a small WebSocket implementation. `fastapi` is not installed in the current environment, so this keeps the service independently runnable while preserving an OpenAPI-compatible contract.

## Scope

- Reuses the existing application/data ideas from `app/services/app_service.py`, `app/services/recognition_pipeline.py`, `app/repositories.py`, `sqls.py`, and `core/sql_helper.py`.
- Exposes REST and WebSocket endpoints for the new web frontend.
- Aligns public payload names with `parallel_work/task-00-contracts/api_contract.yaml` and `event_schema.md`.
- Does not modify `app/`, `services/`, `core/`, `sqls.py`, `main.py`, or `run.py`.

## Start

From the repository root:

```powershell
python parallel_work/task-01-backend-api/main.py --host 127.0.0.1 --port 18080
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:18080/api/health
```

Default local credentials are provided by the legacy DB bootstrap:

```json
{
  "username": "admin",
  "password": "admin"
}
```

Authenticated REST calls require `Authorization: Bearer <token>`. WebSocket channels use `?token=<token>`.

## OpenAPI

Export the OpenAPI document:

```powershell
python parallel_work/task-01-backend-api/scripts/export_openapi.py
```

The exported file is:

```text
parallel_work/task-01-backend-api/openapi.json
```

## REST Endpoints

- `GET /api/health`
- `POST /api/auth/login`
- `GET /api/system/status`
- `GET /api/cameras`
- `POST /api/cameras/start`
- `POST /api/cameras/stop`
- `GET /api/logs`
- `GET /api/attendance`
- `GET /api/faces`
- `POST /api/faces/register`
- `DELETE /api/faces/{name}?retrain=false`
- `POST /api/models/train`
- `GET /openapi.json`

## WebSocket Channels

- `WS /ws/stream/{camera_id}?token=<token>`
  Sends `EventEnvelope` messages with `event_type="camera.frame"` and a `FramePacket` payload containing JPEG base64 frame data.

- `WS /ws/events?token=<token>`
  Sends `EventEnvelope` messages with `event_type="vision.observation"` and a `VisionObservation` payload containing frame metadata, detections, recognitions, emotions, alerts, and `SystemStatus`.

## Contract Notes

The API uses the Task-00 names for externally visible objects:

- `SystemStatus`
- `CameraDescriptor`
- `FramePacket`
- `DetectionResult`
- `RecognitionResult`
- `EmotionResult`
- `AlertResult`
- `VisionObservation`
- `EventEnvelope`

All JSON fields use `snake_case`. Unknown identities are normalized to `unknown`.

## Minimal Self Test

```powershell
python -m unittest discover -s parallel_work/task-01-backend-api/tests
python parallel_work/task-01-backend-api/scripts/export_openapi.py
python parallel_work/task-01-backend-api/scripts/smoke_test.py
```

The smoke test starts the backend on port `18081`, checks `/api/health`, logs in as `admin/admin`, reads `/api/system/status`, and fetches `/openapi.json`.

## Not Yet Connected To Real Recognition

- Camera startup uses OpenCV `VideoCapture` and calls the legacy recognition service, but long-running multi-camera scheduling is still a lightweight adapter, not the planned Task-05 runtime.
- `mode="from_camera"` face enrollment is reserved and currently returns an error; upload-based registration works.
- Tracking IDs are currently per-frame sequential IDs, not stable multi-frame tracks from Task-03.
- WebSocket stream payloads are JSON-wrapped JPEG base64 frames, not a binary or chunked transport.
- Alerting is minimal and only emits `unknown_face` observations from recognition output.
- Model training calls the legacy `AppService.rebuild_and_train()` directly and has not been separated into a queue/job system.
- FastAPI is not used yet because it is not available in the current environment; the public OpenAPI document remains exported and versioned.

## Handoff

For Task-02 frontend:

- Treat `parallel_work/task-01-backend-api/openapi.json` as the local API reference.
- Use `LoginResponse.token` or `LoginResponse.access_token` as the bearer token.
- Use `/ws/stream/{camera_id}` for frame rendering and `/ws/events` for overlays/events.
- Build UI types around the Task-00 names listed above, not around legacy Qt classes.

For Task-08 integration:

- This directory is self-contained and can be copied or mounted as a backend service candidate.
- The adapter currently imports legacy modules directly; integration should decide whether to keep that import path or move shared service facades into a stable package.
- If FastAPI is introduced later, keep the same Pydantic models and path shapes to avoid breaking Task-02.
