# UI Refactor Snapshot

## Entry
- `main.py`: application entry only (font/style constants, app bootstrap, login flow, main-window launch, shutdown hook).

## UI Modules
- `app/ui/monitor_windows.py`: monitor/main window + add/delete camera + enrollment + reset related windows.
- `app/ui/auth_windows.py`: login and register windows.
- `app/ui/log_window.py`: log query/export/attendance-related window.

## Runtime Modules
- `app/runtime/camera_stream.py`: camera stream runtime and recognition rendering loop.

## Wiring
1. `main.py` creates `APP_SERVICE`.
2. `main.py` calls `configure_monitor_windows(APP_SERVICE, DEFAULT_UI_FONT, APP_STYLESHEET)`.
3. Login window launches and validates account.
4. On success, `MWindow` is created from `app/ui/monitor_windows.py`.

This split keeps behavior unchanged while reducing `main.py` from a monolith to a startup script.
