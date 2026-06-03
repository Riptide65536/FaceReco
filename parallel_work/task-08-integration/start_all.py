from __future__ import annotations

import argparse
import subprocess
import sys
import time

from common import (
    REPO_ROOT,
    build_backend_command,
    build_frontend_build_command,
    build_frontend_env,
    build_frontend_long_running_command,
    format_command,
    load_settings,
    terminate_process,
    wait_for_http,
    ws_base_url,
)


def parse_args() -> argparse.Namespace:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Start the integrated backend and frontend together.")
    parser.add_argument("--backend-host", default=settings.backend.host)
    parser.add_argument("--backend-port", default=settings.backend.port, type=int)
    parser.add_argument("--backend-timeout", default=settings.backend.startup_timeout_seconds, type=int)
    parser.add_argument("--frontend-host", default=settings.frontend.host)
    parser.add_argument("--frontend-port", default=settings.frontend.port, type=int)
    parser.add_argument("--frontend-mode", choices=["dev", "preview"], default="dev")
    parser.add_argument("--api-mode", choices=["live", "auto", "mock"], default=settings.frontend.api_mode)
    return parser.parse_args()


def main() -> int:
    settings = load_settings()
    args = parse_args()

    backend_command = build_backend_command(settings, args.backend_host, args.backend_port)
    backend_base_url = f"http://{args.backend_host}:{args.backend_port}"
    backend_health_url = f"{backend_base_url}{settings.backend.health_path}"
    frontend_env = build_frontend_env(
        settings,
        args.api_mode,
        backend_base_url,
        ws_base_url(backend_base_url),
    )

    print("Starting integrated stack...")
    print(f"Backend command: {format_command(backend_command)}")
    print("Cold start may take 20-60 seconds because the recognition models are loaded on boot.")

    backend_process = subprocess.Popen(backend_command, cwd=str(REPO_ROOT))
    frontend_process: subprocess.Popen[object] | None = None

    try:
        wait_for_http(backend_health_url, args.backend_timeout, process=backend_process)
        print(f"Backend ready: {backend_base_url}")

        if args.frontend_mode == "preview":
            build_command = build_frontend_build_command()
            print(f"Frontend build command: {format_command(build_command)}")
            build_result = subprocess.run(
                build_command,
                cwd=str(settings.frontend.workspace),
                env=frontend_env,
                check=False,
            )
            if build_result.returncode != 0:
                return build_result.returncode

        frontend_command = build_frontend_long_running_command(
            args.frontend_mode,
            args.frontend_host,
            args.frontend_port,
        )
        print(f"Frontend command: {format_command(frontend_command)}")
        frontend_process = subprocess.Popen(
            frontend_command,
            cwd=str(settings.frontend.workspace),
            env=frontend_env,
        )

        print(f"Frontend ready at: http://{args.frontend_host}:{args.frontend_port}")
        print("Press Ctrl+C to stop both processes.")

        while True:
            if backend_process.poll() is not None:
                return backend_process.returncode or 1
            if frontend_process.poll() is not None:
                return frontend_process.returncode or 1
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping integrated stack...")
        return 130
    except Exception as exc:
        print(f"Integrated start failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if frontend_process is not None:
            terminate_process(frontend_process, "frontend")
        terminate_process(backend_process, "backend")


if __name__ == "__main__":
    raise SystemExit(main())
