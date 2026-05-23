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
