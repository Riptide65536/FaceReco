from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any
import datetime as dt

import sqls


class ConfigRepository:
    """Read/write legacy txt configs used by existing UI files."""

    def __init__(self, config_dir: str = "config") -> None:
        self.config_dir = Path(config_dir)

    def _read_lines(self, name: str) -> list[str]:
        path = self.config_dir / name
        if not path.exists():
            return []
        return [line.strip("\n") for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()]

    def _write_text(self, name: str, content: str) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / name).write_text(content, encoding="utf-8")

    def load_total_user(self) -> int:
        lines = self._read_lines("totalUser.txt")
        if not lines:
            return 0
        try:
            return int(lines[0])
        except ValueError:
            return 0

    def save_total_user(self, total: int) -> None:
        self._write_text("totalUser.txt", str(int(total)))

    def load_id_lists(self) -> list[int]:
        result: list[int] = []
        for line in self._read_lines("idlists.txt"):
            if line == "":
                continue
            try:
                result.append(int(line))
            except ValueError:
                continue
        return result

    def save_id_lists(self, ids: list[int]) -> None:
        text = "".join(f"{int(i)}\n" for i in ids)
        self._write_text("idlists.txt", text)

    def load_user_dic(self) -> dict[int, str]:
        path = self.config_dir / "userdic.txt"
        if (not path.exists()) or path.stat().st_size == 0:
            return {}
        raw = path.read_text(encoding="utf-8", errors="ignore")
        data = ast.literal_eval(raw)
        result = {}
        for k, v in data.items():
            try:
                result[int(k)] = str(v)
            except Exception:
                continue
        return result

    def save_user_dic(self, user_dic: dict[int, str]) -> None:
        self._write_text("userdic.txt", str(user_dic))

    def load_camera_slot(self, slot: int) -> list[str]:
        return self._read_lines(f"configwin{slot}.txt")

    def save_camera_slot(self, slot: int, name_location: str, display_mode: int, url: Any) -> None:
        payload = f"{name_location}\n{int(display_mode)}\n{url}\n"
        self._write_text(f"configwin{slot}.txt", payload)

    def ensure_dirs(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)


class DataRepository:
    """File-system level helpers for face-data and model files."""

    def __init__(self, data_dir: str = "data", model_dir: str = "model") -> None:
        self.data_dir = Path(data_dir)
        self.model_dir = Path(model_dir)

    def resolve_user_dir(self, user_id: int, username: str) -> Path | None:
        id_dir = self.data_dir / str(user_id)
        name_dir = self.data_dir / str(username)
        if id_dir.is_dir():
            return id_dir
        if name_dir.is_dir():
            return name_dir
        return None

    def iter_user_image_paths(self, user_id: int, username: str):
        user_dir = self.resolve_user_dir(user_id, username)
        if user_dir is None:
            return
        for item in user_dir.iterdir():
            if item.is_file():
                yield item

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def clear_face_data_keep_py(self) -> None:
        if self.data_dir.is_dir():
            for entry in self.data_dir.iterdir():
                if entry.is_dir():
                    for root, dirs, files in os.walk(entry, topdown=False):
                        for f in files:
                            try:
                                Path(root, f).unlink()
                            except OSError:
                                pass
                        for d in dirs:
                            try:
                                Path(root, d).rmdir()
                            except OSError:
                                pass
                    try:
                        entry.rmdir()
                    except OSError:
                        pass
                elif entry.is_file() and entry.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                    try:
                        entry.unlink()
                    except OSError:
                        pass
        else:
            self.data_dir.mkdir(parents=True, exist_ok=True)

    def reset_model_dir(self) -> None:
        if self.model_dir.exists():
            for item in self.model_dir.iterdir():
                if item.is_file():
                    try:
                        item.unlink()
                    except OSError:
                        pass
        else:
            self.model_dir.mkdir(parents=True, exist_ok=True)


class SqlRepository:
    """Unified DB repository for accounts, logs, attendance and model metadata."""

    def __init__(self, db: Any | None = None) -> None:
        self.db = db or sqls.SqlF()

    def close(self) -> None:
        self.db.dbclose()

    def verify_login(self, username: str, password: str) -> bool:
        return bool(self.db.verify_login(username, password))

    def register(self, username: str, password: str) -> bool:
        return bool(self.db.register(username, password))

    def get_all_accounts(self) -> list[tuple[str]]:
        return self.db.getAllaccount()

    def save_recognition_event(
        self,
        name: str,
        location: str,
        timepoint: dt.datetime,
        emotion: str = "中性",
        attendance_type: str | None = None,
    ) -> bool:
        return bool(
            self.db.saveNameTimePic(
                name=name,
                location=location,
                time=timepoint,
                emotion=emotion,
                attendance_type=attendance_type,
            )
        )

    def query_logs_with_emotion(
        self,
        name: str | None = None,
        location: str | None = None,
        start_time: dt.datetime | None = None,
        end_time: dt.datetime | None = None,
        attendance_type: str | None = None,
        status: str | None = None,
    ):
        return self.db.query_logs_with_emotion(
            name=name,
            location=location,
            start_time=start_time,
            end_time=end_time,
            attendance_type=attendance_type,
            status=status,
        )

    def get_absence_list(self, expected_names: list[str], day: dt.date | None = None) -> list[str]:
        return self.db.getAbsenceList(expected_names, day=day)

    def get_attendance_summary(self, start_date: dt.datetime, end_date: dt.datetime):
        return self.db.getAttendanceSummary(start_date, end_date)

    def export_attendance_report(
        self,
        output_path: str,
        name: str | None = None,
        location: str | None = None,
        start_time: dt.datetime | None = None,
        end_time: dt.datetime | None = None,
        attendance_type: str | None = None,
        status: str | None = None,
    ) -> tuple[bool, int]:
        return self.db.exportAttendanceReport(
            output_path=output_path,
            name=name,
            location=location,
            start_time=start_time,
            end_time=end_time,
            attendance_type=attendance_type,
            status=status,
        )

    def save_model_metadata(self, name: str, feature_path: str, label: int | None = None) -> bool:
        return self.db.saveFaceFeature(name, {"label": label, "feature_path": feature_path})
