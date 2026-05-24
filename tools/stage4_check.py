from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def _run(cmd: list[str], cwd: Path, dry_run: bool = False) -> dict[str, Any]:
    started = time.time()
    command_text = " ".join(cmd)
    if dry_run:
        return {
            "cmd": command_text,
            "code": 0,
            "duration_seconds": 0.0,
            "stdout": "[dry-run]",
            "stderr": "",
        }

    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "cmd": command_text,
        "code": int(proc.returncode),
        "duration_seconds": round(time.time() - started, 3),
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage-4 one-click checker")
    parser.add_argument("--skip-doctor", action="store_true", help="skip environment doctor")
    parser.add_argument("--skip-tests", action="store_true", help="skip pytest")
    parser.add_argument("--skip-perf", action="store_true", help="skip performance check")
    parser.add_argument("--dry-run", action="store_true", help="show planned commands only")
    parser.add_argument("--strict", action="store_true", help="non-zero exit if any step fails")
    parser.add_argument("--perf-mode", default="recognize", choices=["detect", "recognize", "recognize_emotion"])
    parser.add_argument("--perf-source", default="0", help="camera index or video path")
    parser.add_argument("--perf-frames", type=int, default=200)
    parser.add_argument("--perf-warmup", type=int, default=20)
    parser.add_argument("--perf-duration-seconds", type=int, default=0, help="if >0, run stability mode")
    parser.add_argument("--perf-report-interval", type=int, default=15)
    parser.add_argument(
        "--output-json",
        default=str(ROOT / "reports" / "stage4_check_report.json"),
        help="path to write the stage-4 summary JSON",
    )
    args = parser.parse_args()

    steps: list[dict[str, Any]] = []
    py = sys.executable

    if not args.skip_doctor:
        steps.append(
            _run([py, str(TOOLS / "doctor.py")], cwd=ROOT, dry_run=args.dry_run)
        )

    if not args.skip_tests:
        steps.append(
            _run([py, "-m", "pytest", "-q"], cwd=ROOT, dry_run=args.dry_run)
        )

    if not args.skip_perf:
        perf_json = str(ROOT / "reports" / "perf_stage4.json")
        perf_cmd = [
            py,
            str(TOOLS / "perf_check.py"),
            "--mode",
            args.perf_mode,
            "--source",
            str(args.perf_source),
            "--output-json",
            perf_json,
        ]
        if args.perf_duration_seconds > 0:
            perf_cmd += [
                "--duration-seconds",
                str(args.perf_duration_seconds),
                "--report-interval",
                str(args.perf_report_interval),
                "--warmup",
                str(max(0, args.perf_warmup)),
            ]
        else:
            perf_cmd += [
                "--frames",
                str(max(10, args.perf_frames)),
                "--warmup",
                str(max(0, args.perf_warmup)),
            ]
        steps.append(_run(perf_cmd, cwd=ROOT, dry_run=args.dry_run))

    failed = [s for s in steps if s["code"] != 0]
    summary = {
        "timestamp_epoch": int(time.time()),
        "python": py,
        "root": str(ROOT),
        "strict": bool(args.strict),
        "dry_run": bool(args.dry_run),
        "step_count": len(steps),
        "failed_count": len(failed),
        "passed": len(failed) == 0,
        "steps": steps,
    }

    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[stage4] summary saved: {out}")

    for idx, s in enumerate(steps, start=1):
        status = "OK" if s["code"] == 0 else "FAIL"
        print(f"[{idx}/{len(steps)}] {status} code={s['code']} {s['cmd']}")
        if s["stdout"]:
            print(s["stdout"][:600])
        if s["stderr"]:
            print(s["stderr"][:300])

    if args.strict and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
