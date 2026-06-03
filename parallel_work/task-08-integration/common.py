from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
CONFIG_PATH = THIS_DIR / "config.json"


@dataclass(frozen=True)
class BackendSettings:
    entry: Path
    host: str
    port: int
    startup_timeout_seconds: int
    health_path: str

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass(frozen=True)
class FrontendSettings:
    workspace: Path
    host: str
    port: int
    api_mode: str

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass(frozen=True)
class LegacySettings:
    entry: Path


@dataclass(frozen=True)
class DemoSettings:
    recommended_camera_slots: list[str]
    notes: list[str]


@dataclass(frozen=True)
class IntegrationSettings:
    python_path: Path
    backend: BackendSettings
    frontend: FrontendSettings
    legacy: LegacySettings
    demo: DemoSettings


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def load_settings() -> IntegrationSettings:
    raw = _read_json(CONFIG_PATH)
    backend = raw["backend"]
    frontend = raw["frontend"]
    legacy = raw["legacy"]
    demo = raw.get("demo", {})
    return IntegrationSettings(
        python_path=resolve_repo_path(raw["python_path"]),
        backend=BackendSettings(
            entry=resolve_repo_path(backend["entry"]),
            host=str(backend["host"]),
            port=int(backend["port"]),
            startup_timeout_seconds=int(backend["startup_timeout_seconds"]),
            health_path=str(backend["health_path"]),
        ),
        frontend=FrontendSettings(
            workspace=resolve_repo_path(frontend["workspace"]),
            host=str(frontend["host"]),
            port=int(frontend["port"]),
            api_mode=str(frontend.get("api_mode", "live")),
        ),
        legacy=LegacySettings(
            entry=resolve_repo_path(legacy["entry"]),
        ),
        demo=DemoSettings(
            recommended_camera_slots=[str(item) for item in demo.get("recommended_camera_slots", [])],
            notes=[str(item) for item in demo.get("notes", [])],
        ),
    )


def npm_executable() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def format_command(command: list[str]) -> str:
    return " ".join(f'"{item}"' if " " in item else item for item in command)


def build_backend_command(settings: IntegrationSettings, host: str, port: int) -> list[str]:
    return [
        str(settings.python_path),
        str(settings.backend.entry),
        "--host",
        host,
        "--port",
        str(port),
    ]


def build_frontend_env(
    settings: IntegrationSettings,
    api_mode: str,
    api_base_url: str,
    ws_base_url: str,
) -> dict[str, str]:
    env = os.environ.copy()
    env["VITE_API_MODE"] = api_mode
    env["VITE_API_BASE_URL"] = api_base_url
    env["VITE_WS_BASE_URL"] = ws_base_url
    return env


def build_frontend_build_command() -> list[str]:
    return [npm_executable(), "run", "build"]


def build_frontend_long_running_command(mode: str, host: str, port: int) -> list[str]:
    if mode == "preview":
        return [npm_executable(), "run", "preview", "--", "--host", host, "--port", str(port)]
    return [npm_executable(), "run", "dev", "--", "--host", host, "--port", str(port)]


def wait_for_http(
    url: str,
    timeout_seconds: float,
    *,
    process: subprocess.Popen[Any] | None = None,
    poll_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"Process exited before {url} became ready. exit_code={process.returncode}")
        try:
            return request_json(url, timeout=5.0)
        except Exception as exc:  # pragma: no cover - polling path
            last_error = exc
            time.sleep(poll_interval_seconds)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    body = None
    final_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        final_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=final_headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def ws_base_url(api_base_url: str) -> str:
    if api_base_url.startswith("https://"):
        return f"wss://{api_base_url[len('https://'):]}"
    if api_base_url.startswith("http://"):
        return f"ws://{api_base_url[len('http://'):]}"
    return api_base_url


def terminate_process(process: subprocess.Popen[Any], name: str) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        pass
    process.kill()
    process.wait(timeout=5)
    print(f"{name} did not exit in time and was killed.", file=sys.stderr)


def port_is_busy(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def read_camera_slot_summaries() -> list[dict[str, str]]:
    config_dir = REPO_ROOT / "config"
    items: list[dict[str, str]] = []
    for slot in range(1, 5):
        path = config_dir / f"configwin{slot}.txt"
        lines: list[str] = []
        if path.exists():
            lines = [line.rstrip("\n") for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()]
        name_location = lines[0] if len(lines) > 0 else ""
        display_mode = lines[1] if len(lines) > 1 else ""
        source = lines[2] if len(lines) > 2 else ""
        items.append(
            {
                "camera_id": str(slot),
                "name_location": name_location,
                "display_mode": display_mode,
                "source": source,
                "configured": "yes" if bool(source.strip()) else "no",
                "config_path": str(path),
            }
        )
    return items


def pick_demo_camera_id(
    cameras_payload: dict[str, Any] | list[dict[str, Any]],
    preferred_slots: list[str],
) -> str | None:
    items = extract_items(cameras_payload)
    cameras = [item for item in items if isinstance(item, dict)]
    by_id = {str(item.get("camera_id", "")): item for item in cameras}
    for slot in preferred_slots:
        item = by_id.get(str(slot))
        if not item:
            continue
        source = str(item.get("source") or item.get("source_uri") or "").strip()
        if source:
            return str(slot)
    for item in cameras:
        source = str(item.get("source") or item.get("source_uri") or "").strip()
        if source:
            return str(item.get("camera_id"))
    return None


def safe_json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def extract_items(payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("items", [])
        return [item for item in items if isinstance(item, dict)]
    return [item for item in payload if isinstance(item, dict)]
