from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class CameraRuntime:
    """Runtime descriptor for one camera slot in main window."""

    slot: int
    label_name: str
    busy_attr: str
    camera_attr: str
    thread: Optional[object] = None
    start_fn: Optional[Callable] = None
    close_fn: Optional[Callable] = None
