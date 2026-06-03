from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from common import load_settings, npm_executable, port_is_busy, read_camera_slot_summaries


def _run(command: list[str], cwd: Path | None = None) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return False, str(exc)
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        return False, output or f"exit code {completed.returncode}"
    return True, output or "ok"


def _print_result(state: str, label: str, detail: str) -> None:
    print(f"[{state}] {label}: {detail}")


def main() -> int:
    settings = load_settings()
    failures = 0

    if settings.python_path.exists():
        _print_result("OK", "FaceReco Python", str(settings.python_path))
    else:
        failures += 1
        _print_result("FAIL", "FaceReco Python", f"missing: {settings.python_path}")

    ok, detail = _run(
        [
            str(settings.python_path),
            "-c",
            "import importlib.util; mods=['PySide2','cv2','pydantic','numpy']; "
            "missing=[m for m in mods if importlib.util.find_spec(m) is None]; "
            "print('missing=' + ','.join(missing) if missing else 'ok')",
        ]
    )
    if ok and detail == "ok":
        _print_result("OK", "Python modules", "PySide2/cv2/pydantic/numpy are available")
    else:
        failures += 1
        _print_result("FAIL", "Python modules", detail)

    for label, command in [("Node.js", ["node", "--version"]), ("npm", [npm_executable(), "--version"])]:
        ok, detail = _run(command)
        if ok:
            _print_result("OK", label, detail)
        else:
            failures += 1
            _print_result("FAIL", label, detail)

    for label, path in [
        ("Task-01 backend entry", settings.backend.entry),
        ("Task-02 frontend workspace", settings.frontend.workspace),
        ("Legacy desktop entry", settings.legacy.entry),
    ]:
        if path.exists():
            _print_result("OK", label, str(path))
        else:
            failures += 1
            _print_result("FAIL", label, f"missing: {path}")

    if port_is_busy(settings.backend.host, settings.backend.port):
        _print_result("WARN", "Backend port", f"{settings.backend.host}:{settings.backend.port} is already in use")
    else:
        _print_result("OK", "Backend port", f"{settings.backend.host}:{settings.backend.port} is free")

    if port_is_busy(settings.frontend.host, settings.frontend.port):
        _print_result("WARN", "Frontend port", f"{settings.frontend.host}:{settings.frontend.port} is already in use")
    else:
        _print_result("OK", "Frontend port", f"{settings.frontend.host}:{settings.frontend.port} is free")

    for item in read_camera_slot_summaries():
        source = item["source"] or "<empty>"
        _print_result(
            "INFO",
            f"Legacy camera slot {item['camera_id']}",
            f"configured={item['configured']} source={source}",
        )

    for note in settings.demo.notes:
        _print_result("INFO", "Demo note", note)

    if failures:
        print(f"\nPreflight failed with {failures} blocking item(s).", file=sys.stderr)
        return 1

    print("\nPreflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
