from __future__ import annotations

import argparse
import subprocess
import sys

from common import (
    build_frontend_build_command,
    build_frontend_env,
    build_frontend_long_running_command,
    format_command,
    load_settings,
    terminate_process,
    ws_base_url,
)


def parse_args() -> argparse.Namespace:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Start the Task-02 frontend in dev or preview mode.")
    parser.add_argument("--mode", choices=["dev", "preview"], default="dev")
    parser.add_argument("--host", default=settings.frontend.host)
    parser.add_argument("--port", default=settings.frontend.port, type=int)
    parser.add_argument("--api-mode", choices=["live", "auto", "mock"], default=settings.frontend.api_mode)
    parser.add_argument("--api-base-url", default=settings.backend.base_url)
    parser.add_argument("--ws-base-url", default="")
    return parser.parse_args()


def main() -> int:
    settings = load_settings()
    args = parse_args()
    ws_url = args.ws_base_url or ws_base_url(args.api_base_url)
    env = build_frontend_env(settings, args.api_mode, args.api_base_url, ws_url)

    if args.mode == "preview":
        build_command = build_frontend_build_command()
        print("Building frontend...")
        print(f"Command: {format_command(build_command)}")
        completed = subprocess.run(build_command, cwd=str(settings.frontend.workspace), env=env, check=False)
        if completed.returncode != 0:
            return completed.returncode

    command = build_frontend_long_running_command(args.mode, args.host, args.port)
    print("Starting frontend...")
    print(f"Command: {format_command(command)}")
    print(f"Frontend URL: http://{args.host}:{args.port}")
    print(f"VITE_API_MODE={args.api_mode}")
    print(f"VITE_API_BASE_URL={args.api_base_url}")
    print(f"VITE_WS_BASE_URL={ws_url}")

    process = subprocess.Popen(command, cwd=str(settings.frontend.workspace), env=env)
    try:
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping frontend...")
        return 130
    finally:
        terminate_process(process, "frontend")


if __name__ == "__main__":
    raise SystemExit(main())
