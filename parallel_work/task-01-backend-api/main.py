from __future__ import annotations

import argparse
import signal
import sys

from backend_api.server import BackendServer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Task-01 backend API service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=18080, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = BackendServer(host=args.host, port=args.port)

    def _shutdown(_signum=None, _frame=None):
        server.shutdown()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    print(f"Task-01 backend API listening on http://{args.host}:{args.port}")
    print(f"OpenAPI: http://{args.host}:{args.port}/openapi.json")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())

