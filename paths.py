from __future__ import annotations

from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / 'ui'
ASSET_DIR = BASE_DIR / 'assets' / 'attachment'
CONFIG_DIR = BASE_DIR / 'config'
MODEL_DIR = BASE_DIR / 'model'
FACE_DATA_DIR = BASE_DIR / 'data'


def ui_path(name: str) -> str:
    return str(UI_DIR / name)


def asset_path(name: str) -> str:
    return str(ASSET_DIR / name)


def config_path(name: str) -> str:
    return str(CONFIG_DIR / name)


def model_path(name: str = 'model.yml') -> str:
    return str(MODEL_DIR / name)


def face_data_path(*parts: str) -> str:
    return str(FACE_DATA_DIR.joinpath(*parts))
