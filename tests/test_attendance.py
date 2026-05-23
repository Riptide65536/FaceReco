import datetime as dt

from services.attendance_service import AttendanceService


def test_first_recognition_before_work_is_check_in_normal():
    service = AttendanceService(work_start="09:00", work_end="18:00")

    result = service.classify("linhao", dt.datetime(2026, 5, 22, 8, 50), [])

    assert result.attendance_type == "上班打卡"
    assert result.status == "正常"


def test_first_recognition_after_work_start_is_late():
    service = AttendanceService(work_start="09:00", work_end="18:00")

    result = service.classify("linhao", dt.datetime(2026, 5, 22, 9, 10), [])

    assert result.attendance_type == "上班打卡"
    assert result.status == "迟到"


def test_evening_second_recognition_is_check_out():
    service = AttendanceService(work_start="09:00", work_end="18:00")
    logs = [{"name": "linhao", "timestamp": dt.datetime(2026, 5, 22, 8, 50), "attendance_type": "上班打卡"}]

    result = service.classify("linhao", dt.datetime(2026, 5, 22, 18, 5), logs)

    assert result.attendance_type == "下班打卡"
    assert result.status == "正常"


def test_detect_absence_from_daily_checkins():
    service = AttendanceService()
    logs = [{"name": "linhao", "timestamp": dt.datetime(2026, 5, 22, 8, 50), "attendance_type": "上班打卡"}]

    absent = service.detect_absence(["linhao", "zxy"], logs, day=dt.date(2026, 5, 22))

    assert absent == ["zxy"]
