from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.runtime.camera_runtime import CameraRuntime


@dataclass
class CameraSlotStartRequest:
    slot: int
    url: Any
    camera_name_place: str = ""
    display_mode: int = 0


class MainUIController:
    """Thin orchestration layer for main window camera slot operations."""

    def __init__(self, main_window: Any) -> None:
        self.main_window = main_window

    def get_slot_runtime(self, slot: int) -> CameraRuntime:
        mapping = {
            1: CameraRuntime(1, "display1", "busy1", "cam1"),
            2: CameraRuntime(2, "display2", "busy2", "cam2"),
            3: CameraRuntime(3, "display3", "busy3", "cam3"),
            4: CameraRuntime(4, "display4", "busy4", "cam4"),
        }
        if slot not in mapping:
            raise ValueError(f"invalid slot: {slot}")
        return mapping[slot]

    def is_slot_busy(self, slot: int) -> bool:
        runtime = self.get_slot_runtime(slot)
        return bool(getattr(self.main_window, runtime.busy_attr, False))

    def set_slot_busy(self, slot: int, busy: bool) -> None:
        runtime = self.get_slot_runtime(slot)
        setattr(self.main_window, runtime.busy_attr, bool(busy))

    def get_slot_camera(self, slot: int):
        runtime = self.get_slot_runtime(slot)
        return getattr(self.main_window, runtime.camera_attr, None)

    def set_slot_camera(self, slot: int, camera_obj: Any) -> None:
        runtime = self.get_slot_runtime(slot)
        setattr(self.main_window, runtime.camera_attr, camera_obj)
