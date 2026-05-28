from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Dict, List


@dataclass
class AppState:
    """Centralized mutable state replacing ad-hoc global variables."""

    system_lock_slot: int = 0
    realtime_mode: str = "balanced"
    show_fps_overlay: bool = False
    custom_attendance_active: bool = False
    custom_attendance_label: str = ""
    custom_attendance_recorded_names: set[str] = field(default_factory=set)
    total_user: int = 0
    face_samples: List = field(default_factory=list)
    id_lists: List[int] = field(default_factory=list)
    user_dic: Dict[int, str] = field(default_factory=dict)
    _custom_attendance_lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def update_user_stats(self) -> None:
        self.total_user = max([int(i) for i in self.user_dic.keys()], default=0)

    def clear_training_cache(self) -> None:
        self.face_samples = []
        self.id_lists = []

    def start_custom_attendance(self, label: str) -> str:
        cleaned = str(label or "").strip()
        with self._custom_attendance_lock:
            self.custom_attendance_active = bool(cleaned)
            self.custom_attendance_label = cleaned
            self.custom_attendance_recorded_names.clear()
        return cleaned

    def stop_custom_attendance(self) -> None:
        with self._custom_attendance_lock:
            self.custom_attendance_active = False
            self.custom_attendance_label = ""
            self.custom_attendance_recorded_names.clear()

    def active_custom_attendance_label(self) -> str:
        with self._custom_attendance_lock:
            if not self.custom_attendance_active:
                return ""
            return str(self.custom_attendance_label or "").strip()

    def has_custom_attendance_recorded(self, name: str) -> bool:
        with self._custom_attendance_lock:
            return str(name or "") in self.custom_attendance_recorded_names

    def try_mark_custom_attendance_recorded(self, name: str) -> bool:
        cleaned = str(name or "").strip()
        if not cleaned:
            return False
        with self._custom_attendance_lock:
            if cleaned in self.custom_attendance_recorded_names:
                return False
            self.custom_attendance_recorded_names.add(cleaned)
            return True

    def mark_custom_attendance_recorded(self, name: str) -> None:
        cleaned = str(name or "").strip()
        if not cleaned:
            return
        with self._custom_attendance_lock:
            self.custom_attendance_recorded_names.add(cleaned)

    def unmark_custom_attendance_recorded(self, name: str) -> None:
        cleaned = str(name or "").strip()
        if not cleaned:
            return
        with self._custom_attendance_lock:
            self.custom_attendance_recorded_names.discard(cleaned)
