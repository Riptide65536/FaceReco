import datetime as dt

from data.sql_helper import SqlF


def test_sqlite_login_register_and_log_query(tmp_path):
    db_path = tmp_path / "test.db"
    sql = SqlF(backend="sqlite", sqlite_path=str(db_path))

    assert sql.register("user1", "secret")
    assert sql.verify_login("user1", "secret")
    assert not sql.verify_login("user1", "wrong")

    now = dt.datetime(2026, 5, 22, 8, 55)
    assert sql.saveNameTimePic("user1", "front-door", now, emotion="中性")

    rows = sql.query_logs(
        name="user1",
        location="front-door",
        start_time=dt.datetime(2026, 5, 22, 0, 0),
        end_time=dt.datetime(2026, 5, 22, 23, 59),
    )
    report = sql.getAttendanceReport(dt.datetime(2026, 5, 22, 0, 0), dt.datetime(2026, 5, 22, 23, 59))

    assert rows == [("user1", "front-door", "2026-05-22 08:55:00")]
    assert report[0]["attendance_type"] == "上班打卡"
    assert report[0]["status"] == "正常"

    sql.dbclose()


def test_sqlite_attendance_records_sync_and_query(tmp_path):
    db_path = tmp_path / "test_attendance.db"
    sql = SqlF(backend="sqlite", sqlite_path=str(db_path))

    base = dt.datetime(2026, 5, 23, 8, 58)
    assert sql.saveNameTimePic("linhao", "gate-a", base, emotion="高兴")
    assert sql.saveAttendanceRecord(
        name="linhao",
        clock_time=dt.datetime(2026, 5, 23, 18, 5),
        attendance_type="下班打卡",
        status="正常",
        location="gate-a",
        emotion="中性",
    )

    records = sql.queryAttendanceByUser(
        "linhao",
        start_time=dt.datetime(2026, 5, 23, 0, 0),
        end_time=dt.datetime(2026, 5, 23, 23, 59),
    )
    assert len(records) >= 2
    assert records[0]["attendance_type"] == "上班打卡"
    assert records[0]["emotion"] == "高兴"
    assert records[-1]["attendance_type"] == "下班打卡"

    sql.dbclose()


def test_query_logs_with_emotion_supports_attendance_filters(tmp_path):
    db_path = tmp_path / "test_log_filters.db"
    sql = SqlF(backend="sqlite", sqlite_path=str(db_path))

    assert sql.saveNameTimePic(
        "alice",
        "front-door",
        dt.datetime(2026, 5, 24, 8, 40),
        emotion="高兴",
        attendance_type="上班打卡",
    )
    assert sql.saveNameTimePic(
        "alice",
        "front-door",
        dt.datetime(2026, 5, 24, 18, 30),
        emotion="中性",
        attendance_type="下班打卡",
    )

    rows = sql.query_logs_with_emotion(
        name="alice",
        location="front-door",
        start_time=dt.datetime(2026, 5, 24, 0, 0),
        end_time=dt.datetime(2026, 5, 24, 23, 59),
        attendance_type="下班打卡",
        status="正常",
    )
    assert len(rows) == 1
    assert rows[0][0] == "alice"
    assert rows[0][4] == "下班打卡"
    assert rows[0][5] == "正常"

    sql.dbclose()


def test_attendance_absence_and_summary_interfaces(tmp_path):
    db_path = tmp_path / "test_attendance_summary.db"
    sql = SqlF(backend="sqlite", sqlite_path=str(db_path))

    day = dt.datetime(2026, 5, 25, 8, 45)
    assert sql.saveNameTimePic("linhao", "gate-a", day, emotion="中性")
    assert sql.saveNameTimePic("linhao", "gate-a", dt.datetime(2026, 5, 25, 18, 10), emotion="高兴")
    assert sql.saveNameTimePic("alice", "gate-b", dt.datetime(2026, 5, 25, 9, 20), emotion="悲伤")

    absences = sql.getAbsenceList(["linhao", "alice", "bob"], day=dt.date(2026, 5, 25))
    assert "bob" in absences
    assert "linhao" not in absences
    assert "alice" not in absences

    summary = sql.getAttendanceSummary(
        dt.datetime(2026, 5, 25, 0, 0),
        dt.datetime(2026, 5, 25, 23, 59),
    )
    assert summary["linhao"]["正常"] >= 1
    # alice's first check-in is after 09:00, should be late
    assert summary["alice"]["迟到"] >= 1

    sql.dbclose()


def test_export_attendance_report_csv(tmp_path):
    db_path = tmp_path / "test_export.db"
    csv_path = tmp_path / "attendance_export.csv"
    sql = SqlF(backend="sqlite", sqlite_path=str(db_path))

    assert sql.saveNameTimePic(
        "linhao",
        "gate-a",
        dt.datetime(2026, 5, 26, 8, 40),
        emotion="高兴",
        attendance_type="上班打卡",
    )
    assert sql.saveNameTimePic(
        "linhao",
        "gate-a",
        dt.datetime(2026, 5, 26, 18, 15),
        emotion="中性",
        attendance_type="下班打卡",
    )

    ok, count = sql.exportAttendanceReport(
        output_path=str(csv_path),
        name="linhao",
        location="gate-a",
        start_time=dt.datetime(2026, 5, 26, 0, 0),
        end_time=dt.datetime(2026, 5, 26, 23, 59),
        attendance_type="任何类型",
        status="任何状态",
    )

    assert ok
    assert count == 2
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "姓名,地点,时间,情绪,考勤类型,状态" in text
    assert "linhao,gate-a,2026-05-26 08:40:00,高兴,上班打卡,正常" in text
    assert "linhao,gate-a,2026-05-26 18:15:00,中性,下班打卡,正常" in text

    sql.dbclose()
