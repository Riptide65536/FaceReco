from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.sql_helper import SqlF


def _scenario_single_person(sql: SqlF) -> tuple[bool, str]:
    base = dt.datetime(2026, 5, 25, 8, 45, 0)
    ok1 = sql.saveNameTimePic("linhao", "gate-a", base, emotion="中性")
    ok2 = sql.saveNameTimePic("linhao", "gate-a", base.replace(hour=18, minute=10), emotion="高兴")
    if not (ok1 and ok2):
        return False, "single person: failed to write logs"
    logs = sql.getAttendanceReport(base.replace(hour=0, minute=0), base.replace(hour=23, minute=59, second=59))
    if len(logs) < 2:
        return False, "single person: expected >=2 logs"
    if logs[0].get("attendance_type") != "上班打卡":
        return False, "single person: first record should be check-in"
    return True, "single person flow ok"


def _scenario_multi_person(sql: SqlF) -> tuple[bool, str]:
    now = dt.datetime(2026, 5, 25, 9, 5, 0)
    ok1 = sql.saveNameTimePic("alice", "gate-b", now, emotion="中性")
    ok2 = sql.saveNameTimePic("bob", "gate-c", now.replace(minute=7), emotion="惊讶")
    if not (ok1 and ok2):
        return False, "multi person: failed to write logs"
    rows = sql.query_logs_with_emotion(
        start_time=now.replace(hour=0, minute=0),
        end_time=now.replace(hour=23, minute=59, second=59),
    )
    names = {row[0] for row in rows}
    if "alice" not in names or "bob" not in names:
        return False, "multi person: missing expected users in query result"
    return True, "multi person aggregation query ok"


def _scenario_absence(sql: SqlF) -> tuple[bool, str]:
    day = dt.date(2026, 5, 25)
    absences = sql.getAbsenceList(["linhao", "alice", "bob", "carol"], day=day)
    if "carol" not in absences:
        return False, "absence: expected carol in absence list"
    return True, "absence detection ok"


def _scenario_filter_and_export(sql: SqlF, output_csv: Path) -> tuple[bool, str]:
    ok, count = sql.exportAttendanceReport(
        output_path=str(output_csv),
        name="linhao",
        location="gate-a",
        start_time=dt.datetime(2026, 5, 25, 0, 0),
        end_time=dt.datetime(2026, 5, 25, 23, 59, 59),
        attendance_type="任何类型",
        status="任何状态",
    )
    if not ok:
        return False, "export: exportAttendanceReport returned False"
    if count <= 0:
        return False, "export: expected >=1 exported row"
    if not output_csv.exists():
        return False, "export: csv file not created"
    return True, f"export ok ({count} rows)"


def run_blackbox(db_path: Path, output_csv: Path) -> dict[str, Any]:
    sql = SqlF(backend="sqlite", sqlite_path=str(db_path))
    sql.resetDB()

    scenarios = [
        ("single_person_flow", _scenario_single_person),
        ("multi_person_flow", _scenario_multi_person),
        ("absence_detection", _scenario_absence),
        ("filter_export", lambda s: _scenario_filter_and_export(s, output_csv)),
    ]

    details = []
    passed = 0
    for name, fn in scenarios:
        ok, message = fn(sql)
        details.append({"name": name, "passed": bool(ok), "message": message})
        if ok:
            passed += 1

    sql.dbclose()
    return {
        "db_path": str(db_path),
        "output_csv": str(output_csv),
        "scenario_count": len(scenarios),
        "passed_count": passed,
        "failed_count": len(scenarios) - passed,
        "passed": passed == len(scenarios),
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage-4 blackbox scenario checker")
    parser.add_argument(
        "--db-path",
        default=str(ROOT / "reports" / "blackbox_check.db"),
        help="sqlite path for scenario checks",
    )
    parser.add_argument(
        "--output-csv",
        default=str(ROOT / "reports" / "blackbox_attendance_export.csv"),
        help="exported csv path for validation",
    )
    parser.add_argument(
        "--output-json",
        default=str(ROOT / "reports" / "blackbox_check_report.json"),
        help="where to write json report",
    )
    args = parser.parse_args()

    result = run_blackbox(Path(args.db_path), Path(args.output_csv))
    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== Blackbox Check ===")
    for item in result["details"]:
        status = "OK" if item["passed"] else "FAIL"
        print(f"{status} {item['name']}: {item['message']}")
    print(f"summary: {result['passed_count']}/{result['scenario_count']} passed")
    print(f"report: {out}")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
