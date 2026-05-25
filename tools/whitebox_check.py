from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import tracemalloc
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.sql_helper import SqlF


def _save_with_retry(sql: SqlF, name: str, retries: int = 3, delay_seconds: float = 0.02) -> bool:
    for idx in range(retries):
        ok = sql.saveNameTimePic(name, "stress-cam", emotion="中性")
        if ok:
            return True
        if idx < retries - 1:
            time.sleep(delay_seconds)
    return False


def _worker(db_path: str, prefix: str, loops: int, errors: list[str], lock: threading.Lock) -> None:
    sql = SqlF(backend="sqlite", sqlite_path=db_path)
    for i in range(loops):
        name = f"{prefix}_{i % 4}"
        try:
            ok = _save_with_retry(sql, name)
            if not ok:
                with lock:
                    errors.append(f"saveNameTimePic returned False for {name}")
        except Exception as exc:
            with lock:
                errors.append(str(exc))
    sql.dbclose()


def run_whitebox(
    db_path: Path,
    threads: int,
    loops_per_thread: int,
    timeout_seconds: int,
    mem_limit_mb: float,
) -> dict[str, Any]:
    sql_init = SqlF(backend="sqlite", sqlite_path=str(db_path))
    sql_init.resetDB()
    sql_init.dbclose()

    errors: list[str] = []
    guard = threading.Lock()
    workers: list[threading.Thread] = []

    tracemalloc.start()
    start_snap = tracemalloc.take_snapshot()
    started = time.time()

    for idx in range(threads):
        t = threading.Thread(
            target=_worker,
            args=(str(db_path), f"user{idx}", loops_per_thread, errors, guard),
            daemon=True,
        )
        workers.append(t)
        t.start()

    timed_out = False
    for t in workers:
        t.join(timeout=timeout_seconds)
        if t.is_alive():
            timed_out = True

    elapsed = time.time() - started
    end_snap = tracemalloc.take_snapshot()
    tracemalloc.stop()

    diff = end_snap.compare_to(start_snap, "lineno")
    total_bytes = sum(stat.size_diff for stat in diff)
    mem_growth_mb = total_bytes / (1024 * 1024)
    sql_verify = SqlF(backend="sqlite", sqlite_path=str(db_path))
    rows = sql_verify.tableWidgetDisplay()
    sql_verify.dbclose()

    passed = not timed_out and not errors and mem_growth_mb <= mem_limit_mb
    return {
        "db_path": str(db_path),
        "threads": threads,
        "loops_per_thread": loops_per_thread,
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": round(elapsed, 3),
        "timed_out": timed_out,
        "error_count": len(errors),
        "errors": errors[:20],
        "written_rows_preview_count": len(rows),
        "memory_growth_mb": round(mem_growth_mb, 3),
        "memory_limit_mb": mem_limit_mb,
        "pass_memory_growth": mem_growth_mb <= mem_limit_mb,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage-4 whitebox concurrency checker")
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--loops-per-thread", type=int, default=60)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--memory-limit-mb", type=float, default=50.0)
    parser.add_argument(
        "--db-path",
        default=str(ROOT / "reports" / "whitebox_check.db"),
        help="sqlite path for whitebox checks",
    )
    parser.add_argument(
        "--output-json",
        default=str(ROOT / "reports" / "whitebox_check_report.json"),
        help="where to write json report",
    )
    args = parser.parse_args()

    result = run_whitebox(
        db_path=Path(args.db_path),
        threads=max(1, args.threads),
        loops_per_thread=max(1, args.loops_per_thread),
        timeout_seconds=max(1, args.timeout_seconds),
        mem_limit_mb=max(1.0, args.memory_limit_mb),
    )

    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== Whitebox Check ===")
    print(f"threads={result['threads']}, loops_per_thread={result['loops_per_thread']}")
    print(f"elapsed_seconds={result['elapsed_seconds']}")
    print(f"timed_out={result['timed_out']}")
    print(f"error_count={result['error_count']}")
    print(f"memory_growth_mb={result['memory_growth_mb']}, limit={result['memory_limit_mb']}")
    print(f"report: {out}")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
