from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any


systemLock = Lock()


@dataclass
class CameraConfig:
    name: str
    url: Any
    location: str = ""
    displaymode: int = 0
    model: str = ""


class CameraService:
    """Stores camera configuration and guards shared camera resources."""

    def __init__(self, config_path: str = "config.json", max_cameras: int = 4) -> None:
        self.config_path = Path(config_path)
        self.max_cameras = max_cameras
        self.cameras: list[CameraConfig] = []
        self.load()

    def add_camera(self, camera: CameraConfig) -> None:
        if len(self.cameras) >= self.max_cameras:
            raise ValueError("最多同时支持 4 路视频流")
        if any(item.url == camera.url for item in self.cameras):
            raise ValueError("摄像头地址已存在")
        self.cameras.append(camera)
        self.save()

    def remove_camera(self, url: Any) -> bool:
        before = len(self.cameras)
        self.cameras = [camera for camera in self.cameras if camera.url != url]
        changed = len(self.cameras) != before
        if changed:
            self.save()
        return changed

    def save(self) -> None:
        self.config_path.write_text(
            json.dumps({"cameras": [asdict(camera) for camera in self.cameras]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self) -> None:
        if not self.config_path.exists():
            self.cameras = []
            return
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.cameras = [CameraConfig(**item) for item in data.get("cameras", [])]
