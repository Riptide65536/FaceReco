from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class CameraSlotConfig:
    name_location: str = ""
    displaymode: int = 0
    url: str = ""


class ConfigManager:
    """Read/write camera config from config.json and legacy configwin files."""

    def __init__(self, json_path: str = "config.json", legacy_dir: str = "config", slot_count: int = 4) -> None:
        self.json_path = Path(json_path)
        self.legacy_dir = Path(legacy_dir)
        self.slot_count = slot_count

    def load(self) -> list[CameraSlotConfig]:
        if self.json_path.exists():
            return self._load_json()
        slots = self._load_legacy()
        if any(slot.url or slot.name_location for slot in slots):
            self.save(slots)
        return slots

    def save(self, slots: list[CameraSlotConfig]) -> None:
        normalized = self._normalize_slots(slots)
        self.json_path.write_text(
            json.dumps({"cameras": [asdict(slot) for slot in normalized]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._save_legacy(normalized)

    def _load_json(self) -> list[CameraSlotConfig]:
        data = json.loads(self.json_path.read_text(encoding="utf-8"))
        return self._normalize_slots([
            CameraSlotConfig(
                name_location=str(item.get("name_location", item.get("name", ""))),
                displaymode=self._safe_int(item.get("displaymode", 0)),
                url=str(item.get("url", "")),
            )
            for item in data.get("cameras", [])
        ])

    def _load_legacy(self) -> list[CameraSlotConfig]:
        slots = []
        for index in range(1, self.slot_count + 1):
            path = self.legacy_dir / f"configwin{index}.txt"
            if not path.exists():
                slots.append(CameraSlotConfig())
                continue
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            slots.append(CameraSlotConfig(
                name_location=lines[0] if len(lines) > 0 else "",
                displaymode=self._safe_int(lines[1] if len(lines) > 1 else 0),
                url=lines[2] if len(lines) > 2 else "",
            ))
        return self._normalize_slots(slots)

    def _save_legacy(self, slots: list[CameraSlotConfig]) -> None:
        self.legacy_dir.mkdir(parents=True, exist_ok=True)
        for index, slot in enumerate(self._normalize_slots(slots), start=1):
            (self.legacy_dir / f"configwin{index}.txt").write_text(
                f"{slot.name_location}\n{slot.displaymode}\n{slot.url}\n",
                encoding="utf-8",
            )

    def _normalize_slots(self, slots: list[CameraSlotConfig]) -> list[CameraSlotConfig]:
        normalized = list(slots[: self.slot_count])
        while len(normalized) < self.slot_count:
            normalized.append(CameraSlotConfig())
        return normalized

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
