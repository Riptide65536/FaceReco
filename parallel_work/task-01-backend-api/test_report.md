# Task-01 Test Report

Date: 2026-06-04

## Scope Checked

- Backend source compiles inside `parallel_work/task-01-backend-api/backend_api`.
- OpenAPI generation includes the Task-00 contract objects and required REST/WebSocket paths.
- Smoke test starts the backend independently and calls real HTTP endpoints.

## Commands

```powershell
python -m compileall parallel_work/task-01-backend-api/backend_api
python -m unittest discover -s parallel_work/task-01-backend-api/tests
python parallel_work/task-01-backend-api/scripts/export_openapi.py
python parallel_work/task-01-backend-api/scripts/smoke_test.py
```

## Actual Results

All checks below passed on 2026-06-04:

```text
python -m compileall parallel_work/task-01-backend-api/backend_api
  PASS

python -m unittest discover -s parallel_work/task-01-backend-api/tests
  PASS: Ran 1 test in 0.023s

python parallel_work/task-01-backend-api/scripts/export_openapi.py
  PASS: wrote parallel_work/task-01-backend-api/openapi.json

python parallel_work/task-01-backend-api/scripts/smoke_test.py
  PASS: health ok, admin login ok, system status ok, OpenAPI fetch ok
  Observed backend_mode: deep
```

## Acceptance Results

- Compile succeeds without syntax/import errors.
- Unit tests confirm required paths, bearer auth, `SystemStatus`, `EventEnvelope`, and `VisionObservation` are present in OpenAPI.
- `export_openapi.py` writes `parallel_work/task-01-backend-api/openapi.json`.
- `smoke_test.py` starts the service on `127.0.0.1:18081`, confirms `/api/health`, logs in with `admin/admin`, reads `/api/system/status`, and reads `/openapi.json`.

## Real Recognition Integration Status

- Connected: login, DB bootstrap, log query, attendance summary, face library listing, upload-based face registration, face deletion, and model training through legacy data/service layers.
- Partially connected: camera start/stop, frame streaming, recognition analysis, emotion prediction, and recognition log persistence.
- Not yet connected: stable tracking, from-camera enrollment session capture, Task-05 decoupled stream runtime, production alert bus, binary stream transport, and queued model training jobs.

## Notes

This task intentionally does not modify the legacy desktop project. The API adapter imports legacy modules and should be integrated by Task-08 after cross-task contract review.
