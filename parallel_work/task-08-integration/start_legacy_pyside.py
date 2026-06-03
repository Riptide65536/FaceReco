from __future__ import annotations

import subprocess

from common import format_command, load_settings, terminate_process


def main() -> int:
    settings = load_settings()
    command = [str(settings.python_path), str(settings.legacy.entry)]
    print("Starting legacy PySide2 desktop fallback...")
    print(f"Command: {format_command(command)}")
    process = subprocess.Popen(command, cwd=str(settings.legacy.entry.parent))
    try:
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping legacy desktop...")
        return 130
    finally:
        terminate_process(process, "legacy desktop")


if __name__ == "__main__":
    raise SystemExit(main())
