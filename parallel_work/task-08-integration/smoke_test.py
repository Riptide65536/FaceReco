from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta
from urllib.error import HTTPError

from common import (
    REPO_ROOT,
    build_backend_command,
    build_frontend_build_command,
    extract_items,
    load_settings,
    pick_demo_camera_id,
    request_json,
    safe_json_dumps,
    terminate_process,
    wait_for_http,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local integration rehearsal for Task-08.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=18090, type=int)
    parser.add_argument("--timeout", default=120, type=int)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    return parser.parse_args()


def main() -> int:
    settings = load_settings()
    args = parse_args()

    build_result = subprocess.run(
        build_frontend_build_command(),
        cwd=str(settings.frontend.workspace),
        check=False,
    )
    if build_result.returncode != 0:
        print("Frontend build failed.", file=sys.stderr)
        return build_result.returncode

    backend_command = build_backend_command(settings, args.host, args.port)
    backend_process = subprocess.Popen(backend_command, cwd=str(REPO_ROOT))
    backend_base_url = f"http://{args.host}:{args.port}"
    health_url = f"{backend_base_url}{settings.backend.health_path}"

    summary: dict[str, object] = {
        "backend_base_url": backend_base_url,
        "frontend_build": "passed",
    }

    try:
        health = wait_for_http(health_url, args.timeout, process=backend_process)
        summary["health"] = health

        login = request_json(
            f"{backend_base_url}/api/auth/login",
            method="POST",
            payload={"username": args.username, "password": args.password},
            timeout=10.0,
        )
        token = str(login.get("access_token") or login.get("token") or "")
        headers = {"Authorization": f"Bearer {token}"}
        summary["login_username"] = login.get("username")

        system_status = request_json(f"{backend_base_url}/api/system/status", headers=headers, timeout=15.0)
        cameras = request_json(f"{backend_base_url}/api/cameras", headers=headers, timeout=15.0)
        logs = request_json(
            f"{backend_base_url}/api/logs?page=1&page_size=5",
            headers=headers,
            timeout=15.0,
        )

        now = datetime.now()
        start_time = (now - timedelta(days=2)).replace(microsecond=0).isoformat()
        end_time = now.replace(microsecond=0).isoformat()
        attendance = request_json(
            f"{backend_base_url}/api/attendance?start_time={start_time}&end_time={end_time}",
            headers=headers,
            timeout=20.0,
        )
        faces = request_json(f"{backend_base_url}/api/faces", headers=headers, timeout=15.0)

        summary["system_backend_mode"] = system_status.get("recognition_backend_mode", system_status.get("backend_mode"))
        summary["camera_count"] = len(extract_items(cameras))
        summary["log_items"] = len(logs.get("items", []))
        summary["attendance_keys"] = sorted(list(attendance.keys()))
        summary["face_items"] = len(faces.get("items", []))

        camera_id = pick_demo_camera_id(cameras, settings.demo.recommended_camera_slots)
        if camera_id is not None:
            try:
                start_response = request_json(
                    f"{backend_base_url}/api/cameras/start",
                    method="POST",
                    headers=headers,
                    payload={"camera_id": camera_id},
                    timeout=20.0,
                )
                time.sleep(3.0)
                stop_response = request_json(
                    f"{backend_base_url}/api/cameras/stop",
                    method="POST",
                    headers=headers,
                    payload={"camera_id": camera_id},
                    timeout=20.0,
                )
                summary["camera_rehearsal"] = {
                    "camera_id": camera_id,
                    "start": start_response,
                    "stop": stop_response,
                }
            except HTTPError as exc:
                summary["camera_rehearsal"] = {
                    "camera_id": camera_id,
                    "error": f"{exc.code} {exc.reason}",
                }
        else:
            summary["camera_rehearsal"] = {
                "skipped": True,
                "reason": "No configured camera source was discovered from /api/cameras.",
            }

        print(safe_json_dumps(summary))
        return 0
    except Exception as exc:
        summary["error"] = str(exc)
        print(safe_json_dumps(summary), file=sys.stderr)
        return 1
    finally:
        terminate_process(backend_process, "backend")


if __name__ == "__main__":
    raise SystemExit(main())
