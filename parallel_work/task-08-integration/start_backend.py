from __future__ import annotations

import argparse
import subprocess
import sys

from common import REPO_ROOT, build_backend_command, format_command, load_settings, terminate_process, wait_for_http


def parse_args() -> argparse.Namespace:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Start the Task-01 backend with the FaceReco Python environment.")
    parser.add_argument("--host", default=settings.backend.host)
    parser.add_argument("--port", default=settings.backend.port, type=int)
    parser.add_argument("--timeout", default=settings.backend.startup_timeout_seconds, type=int)
    parser.add_argument("--skip-health-wait", action="store_true")
    return parser.parse_args()


def main() -> int:
    settings = load_settings()
    args = parse_args()
    command = build_backend_command(settings, args.host, args.port)
    base_url = f"http://{args.host}:{args.port}"
    health_url = f"{base_url}{settings.backend.health_path}"

    print("Starting backend...")
    print(f"Command: {format_command(command)}")
    print("Cold start may take 20-60 seconds because the legacy models are loaded on boot.")

    process = subprocess.Popen(command, cwd=str(REPO_ROOT))
    try:
        if not args.skip_health_wait:
            wait_for_http(health_url, args.timeout, process=process)
            print(f"Backend ready: {base_url}")
            print(f"Health check: {health_url}")
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping backend...")
        return 130
    except Exception as exc:
        print(f"Backend failed to start cleanly: {exc}", file=sys.stderr)
        return 1
    finally:
        terminate_process(process, "backend")


if __name__ == "__main__":
    raise SystemExit(main())
