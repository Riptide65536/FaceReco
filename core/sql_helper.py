from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import logging
import os
import sqlite3
from typing import Any, Optional

from services.attendance_service import AttendanceService

try:
    import pymysql
except Exception:
    pymysql = None


LOGGER = logging.getLogger(__name__)


class SqlF:
    """Database facade used by the legacy UI and service tests."""

    def __init__(self, backend: Optional[str] = None, sqlite_path: Optional[str] = None):
        self.backend = (backend or os.getenv("FACE_DB_BACKEND", "auto")).lower()
        self.sqlite_path = sqlite_path or os.getenv("FACE_DB_SQLITE_PATH", "facial_system.db")
        self.db: Any = None
        self.cursor: Any = None
        self.param = "%s"
        self.attendance = AttendanceService()
        self._connect()
        self._init_schema()

    def _connect(self) -> None:
        if self.backend in {"mysql", "auto"} and pymysql is not None:
            try:
                self.db = pymysql.connect(
                    host=os.getenv("FACE_DB_HOST", "localhost"),
                    port=int(os.getenv("FACE_DB_PORT", "3307")),
                    user=os.getenv("FACE_DB_USER", "root"),
                    password=os.getenv("FACE_DB_PASSWORD", "password"),
                    database=os.getenv("FACE_DB_NAME", "db_bishe"),
                    charset="utf8mb4",
                    autocommit=False,
                )
                self.cursor = self.db.cursor()
                self.backend = "mysql"
                self.param = "%s"
                return
            except Exception as exc:
                if self.backend == "mysql":
                    raise
                LOGGER.warning("MySQL unavailable, falling back to SQLite: %s", exc)

        self.db = sqlite3.connect(self.sqlite_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self.cursor = self.db.cursor()
        self.backend = "sqlite"
        self.param = "?"

    def _init_schema(self) -> None:
        if self.backend == "mysql":
            statements = [
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS recognition_logs (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    name VARCHAR(100),
                    location VARCHAR(100),
                    timestamp DATETIME,
                    emotion VARCHAR(20),
                    attendance_type VARCHAR(20),
                    status VARCHAR(20),
                    image_path VARCHAR(255)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS face_features (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    name VARCHAR(100),
                    label INT,
                    feature_path VARCHAR(255)
                )
                """,
            ]
        else:
            statements = [
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS recognition_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    location TEXT,
                    timestamp TEXT,
                    emotion TEXT,
                    attendance_type TEXT,
                    status TEXT,
                    image_path TEXT
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS face_features (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    label INTEGER,
                    feature_path TEXT
                )
                """,
            ]
        for statement in statements:
            self.cursor.execute(statement)
        self.db.commit()
        self._ensure_default_admin()

    def _ensure_default_admin(self) -> None:
        if self.loginAccountPassword("admin") is None:
            self.register("admin", os.getenv("FACE_DEFAULT_ADMIN_PASSWORD", "admin"))

    def loginAccountPassword(self, username: str, password: Optional[str] = None):
        self.cursor.execute(f"SELECT password FROM accounts WHERE username = {self.param}", (username,))
        result = self.cursor.fetchone()
        if password is None:
            return result
        return bool(result and self._verify_password(password, result[0]))

    def verify_login(self, username: str, password: str) -> bool:
        return bool(self.loginAccountPassword(username, password))

    def register(self, username: str, password: str) -> bool:
        try:
            self.cursor.execute(
                f"INSERT INTO accounts(username, password) VALUES ({self.param}, {self.param})",
                (username, self._hash_password(password)),
            )
            self.db.commit()
            return True
        except Exception as exc:
            self.db.rollback()
            LOGGER.warning("Register failed for %s: %s", username, exc)
            return False

    def getAllaccount(self) -> list[tuple[str]]:
        self.cursor.execute("SELECT DISTINCT username FROM accounts ORDER BY username")
        return self.cursor.fetchall()

    def saveNameTimePic(
        self,
        name: str,
        location: str,
        time: Optional[_dt.datetime] = None,
        emotion: str = "中性",
        attendance_type: Optional[str] = None,
        image_path: Optional[str] = None,
    ) -> bool:
        timestamp = self._coerce_datetime(time)
        existing = self.getAttendanceReport(
            timestamp.replace(hour=0, minute=0, second=0, microsecond=0),
            timestamp.replace(hour=23, minute=59, second=59, microsecond=999999),
        )
        attendance = self.attendance.classify(name, timestamp, existing)
        attendance_type = attendance_type or attendance.attendance_type
        try:
            self.cursor.execute(
                f"""
                INSERT INTO recognition_logs
                    (name, location, timestamp, emotion, attendance_type, status, image_path)
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                """,
                (
                    name,
                    location,
                    self._format_datetime(timestamp),
                    emotion,
                    attendance_type,
                    attendance.status,
                    image_path,
                ),
            )
            self.db.commit()
            return True
        except Exception as exc:
            self.db.rollback()
            LOGGER.exception("Failed to save recognition log: %s", exc)
            return False

    def resetDB(self) -> bool:
        try:
            self.cursor.execute("DELETE FROM recognition_logs")
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    def tableWidgetDisplay(self) -> list[tuple[Any, Any, Any]]:
        self.cursor.execute("SELECT name, location, timestamp FROM recognition_logs ORDER BY timestamp DESC LIMIT 100")
        return self.cursor.fetchall()

    def getAllname(self) -> list[tuple[str]]:
        self.cursor.execute("SELECT DISTINCT name FROM recognition_logs WHERE name IS NOT NULL ORDER BY name")
        return self.cursor.fetchall()

    def getAllplace(self) -> list[tuple[str]]:
        self.cursor.execute("SELECT DISTINCT location FROM recognition_logs WHERE location IS NOT NULL ORDER BY location")
        return self.cursor.fetchall()

    def query_logs(
        self,
        name: Optional[str] = None,
        location: Optional[str] = None,
        start_time: Optional[_dt.datetime] = None,
        end_time: Optional[_dt.datetime] = None,
    ) -> list[tuple[Any, Any, Any]]:
        clauses = []
        params: list[Any] = []
        if name and name != "任何人员":
            clauses.append(f"name = {self.param}")
            params.append(name)
        if location and location != "任何地点":
            clauses.append(f"location = {self.param}")
            params.append(location)
        if start_time and end_time:
            clauses.append(f"timestamp BETWEEN {self.param} AND {self.param}")
            params.extend([self._format_datetime(start_time), self._format_datetime(end_time)])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        self.cursor.execute(
            "SELECT name, location, timestamp FROM recognition_logs" + where + " ORDER BY timestamp DESC",
            tuple(params),
        )
        return self.cursor.fetchall()

    def query_logs_with_emotion(
        self,
        name: Optional[str] = None,
        location: Optional[str] = None,
        start_time: Optional[_dt.datetime] = None,
        end_time: Optional[_dt.datetime] = None,
    ) -> list[tuple[Any, Any, Any, Any]]:
        clauses = []
        params: list[Any] = []
        if name and name != "任何人员":
            clauses.append(f"name = {self.param}")
            params.append(name)
        if location and location != "任何地点":
            clauses.append(f"location = {self.param}")
            params.append(location)
        if start_time and end_time:
            clauses.append(f"timestamp BETWEEN {self.param} AND {self.param}")
            params.extend([self._format_datetime(start_time), self._format_datetime(end_time)])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        self.cursor.execute(
            "SELECT name, location, timestamp, emotion FROM recognition_logs" + where + " ORDER BY timestamp DESC",
            tuple(params),
        )
        return self.cursor.fetchall()

    def saveFaceFeature(self, name: str, feature_matrix: Any) -> bool:
        label = None
        feature_path = str(feature_matrix)
        if isinstance(feature_matrix, dict):
            label = feature_matrix.get("label")
            feature_path = str(feature_matrix.get("feature_path", ""))
        try:
            self.cursor.execute(
                f"INSERT INTO face_features(name, label, feature_path) VALUES ({self.param}, {self.param}, {self.param})",
                (name, label, feature_path),
            )
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    def getAttendanceReport(self, start_date: Any, end_date: Any) -> list[dict[str, Any]]:
        start = self._format_datetime(self._coerce_datetime(start_date))
        end = self._format_datetime(self._coerce_datetime(end_date))
        self.cursor.execute(
            f"""
            SELECT name, location, timestamp, emotion, attendance_type, status, image_path
            FROM recognition_logs
            WHERE timestamp BETWEEN {self.param} AND {self.param}
            ORDER BY timestamp ASC
            """,
            (start, end),
        )
        rows = self.cursor.fetchall()
        return [
            {
                "name": row[0],
                "location": row[1],
                "timestamp": self._coerce_datetime(row[2]),
                "emotion": row[3],
                "attendance_type": row[4],
                "status": row[5],
                "image_path": row[6],
            }
            for row in rows
        ]

    def dbclose(self) -> None:
        if self.db is not None:
            self.db.close()

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
        return "pbkdf2_sha256$120000$%s$%s" % (salt.hex(), digest.hex())

    @staticmethod
    def _verify_password(password: str, stored: str) -> bool:
        if not stored.startswith("pbkdf2_sha256$"):
            return password == stored
        _, iterations, salt_hex, digest_hex = stored.split("$", 3)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)

    @staticmethod
    def _coerce_datetime(value: Any) -> _dt.datetime:
        if value is None:
            return _dt.datetime.now()
        if isinstance(value, _dt.datetime):
            return value
        if isinstance(value, _dt.date):
            return _dt.datetime.combine(value, _dt.time())
        if isinstance(value, str):
            text = value.split(".")[0]
            try:
                return _dt.datetime.fromisoformat(text)
            except ValueError:
                return _dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return value

    @staticmethod
    def _format_datetime(value: _dt.datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")
