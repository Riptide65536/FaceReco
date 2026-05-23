from __future__ import annotations

import datetime as _dt
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class AttendanceResult:
    attendance_type: str
    status: str


class AttendanceService:
    """Encapsulates attendance decisions for recognition events."""

    def __init__(
        self,
        work_start: str = "09:00",
        work_end: str = "18:00",
        checkout_grace_minutes: int = 30,
    ) -> None:
        self.work_start = self._parse_time(work_start)
        self.work_end = self._parse_time(work_end)
        self.checkout_grace = _dt.timedelta(minutes=checkout_grace_minutes)

    def classify(
        self,
        name: str,
        timestamp: _dt.datetime,
        existing_logs: Iterable[dict],
    ) -> AttendanceResult:
        if not name or name.lower() == "unknown":
            return AttendanceResult("未识别", "异常")

        todays_logs = [
            row for row in existing_logs
            if row.get("name") == name and self._same_day(row.get("timestamp"), timestamp)
        ]

        if not todays_logs:
            status = "迟到" if timestamp.time() > self.work_start else "正常"
            return AttendanceResult("上班打卡", status)

        if timestamp.time() >= self.work_end:
            return AttendanceResult("下班打卡", "正常")

        if timestamp.time() >= (
            _dt.datetime.combine(timestamp.date(), self.work_end) - self.checkout_grace
        ).time():
            return AttendanceResult("下班打卡", "早退")

        return AttendanceResult("重复识别", "已记录")

    def detect_absence(
        self,
        expected_names: Iterable[str],
        logs: Iterable[dict],
        day: Optional[_dt.date] = None,
    ) -> list[str]:
        day = day or _dt.date.today()
        present = {
            row.get("name") for row in logs
            if self._same_day(row.get("timestamp"), _dt.datetime.combine(day, _dt.time()))
            and row.get("attendance_type") == "上班打卡"
        }
        return [name for name in expected_names if name not in present]

    def summary_by_person(self, logs: Iterable[dict]) -> dict[str, dict[str, int]]:
        summary: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for row in logs:
            name = row.get("name") or "未知"
            status = row.get("status") or row.get("attendance_type") or "未分类"
            summary[name][status] += 1
        return {name: dict(counts) for name, counts in summary.items()}

    @staticmethod
    def _parse_time(value: str) -> _dt.time:
        return _dt.datetime.strptime(value, "%H:%M").time()

    @staticmethod
    def _same_day(value: object, target: _dt.datetime) -> bool:
        if isinstance(value, str):
            try:
                value = _dt.datetime.fromisoformat(value)
            except ValueError:
                return False
        if isinstance(value, _dt.datetime):
            return value.date() == target.date()
        if isinstance(value, _dt.date):
            return value == target.date()
        return False
