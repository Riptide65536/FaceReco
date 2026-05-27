from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class AppState:
    """Centralized mutable state replacing ad-hoc global variables."""

    system_lock_slot: int = 0
    realtime_mode: str = "balanced"
    show_fps_overlay: bool = False
    total_user: int = 0
    face_samples: List = field(default_factory=list)
    id_lists: List[int] = field(default_factory=list)
    user_dic: Dict[int, str] = field(default_factory=dict)

    def update_user_stats(self) -> None:
        self.total_user = max([int(i) for i in self.user_dic.keys()], default=0)

    def clear_training_cache(self) -> None:
        self.face_samples = []
        self.id_lists = []
