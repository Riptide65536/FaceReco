from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SERVER_CMD = [sys.executable, str(ROOT / "main.py"), "--host", "127.0.0.1", "--port", "18081"]


def wait_for_health(url: str, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Health check did not pass: {last_error}")


def request_json(url: str, *, method: str = "GET", headers: dict | None = None, payload: dict | None = None) -> dict:
    data = None
    final_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        final_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=final_headers, method=method)
    with urllib.request.urlopen(req, timeout=5.0) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    export_script = ROOT / "scripts" / "export_openapi.py"
    subprocess.run([sys.executable, str(export_script)], check=True, cwd=str(ROOT))

    process = subprocess.Popen(
        SERVER_CMD,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        health = wait_for_health("http://127.0.0.1:18081/api/health")
        login = request_json(
            "http://127.0.0.1:18081/api/auth/login",
            method="POST",
            payload={"username": "admin", "password": "admin"},
        )
        token = login["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        status = request_json("http://127.0.0.1:18081/api/system/status", headers=headers)
        openapi = request_json("http://127.0.0.1:18081/openapi.json")
        result = {
            "health": health,
            "login_username": login["username"],
            "status_backend_mode": status["backend_mode"],
            "openapi_title": openapi["info"]["title"],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
