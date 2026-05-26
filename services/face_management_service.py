from __future__ import annotations

import ast
import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from paths import CONFIG_DIR, FACE_DATA_DIR, MODEL_DIR
from services.face_recognition_service import FaceRecognitionService


class FaceManagementService:
    """Loads, deletes and trains local LBPH face datasets."""

    def __init__(
        self,
        data_dir: str = str(FACE_DATA_DIR),
        config_dir: str = str(CONFIG_DIR),
        model_path: str = str(Path(MODEL_DIR) / "model.yml"),
    ) -> None:
        self.data_dir = Path(data_dir)
        self.config_dir = Path(config_dir)
        self.model_path = Path(model_path)

    def load_label_map(self) -> dict[int, str]:
        path = self.config_dir / "userdic.txt"
        if not path.exists() or path.stat().st_size == 0:
            return {}
        return {int(k): v for k, v in ast.literal_eval(path.read_text(encoding="utf-8")).items()}

    def collect_samples(self) -> tuple[list[np.ndarray], list[int], dict[int, str]]:
        labels = self.load_label_map()
        service = FaceRecognitionService(model_path=str(self.model_path), labels=labels)
        samples: list[np.ndarray] = []
        ids: list[int] = []
        for label, name in labels.items():
            person_dir = self.data_dir / name
            if not person_dir.exists():
                continue
            for image_path in person_dir.glob("*.jpg"):
                image = Image.open(image_path).convert("L")
                gray = np.array(image)
                faces = service.detect_faces(gray)
                if not faces:
                    samples.append(gray)
                    ids.append(label)
                    continue
                for x, y, w, h in faces:
                    samples.append(gray[y:y + h, x:x + w])
                    ids.append(label)
        return samples, ids, labels

    def train_all(self) -> int:
        samples, labels, label_map = self.collect_samples()
        service = FaceRecognitionService(model_path=str(self.model_path), labels=label_map)
        service.train(samples, labels)
        self._write_id_list(labels)
        return len(samples)

    def delete_person(self, name: str) -> bool:
        target = self.data_dir / name
        if target.exists():
            shutil.rmtree(target)
        labels = {label: value for label, value in self.load_label_map().items() if value != name}
        self._write_label_map(labels)
        samples, ids, _ = self.collect_samples()
        if samples:
            FaceRecognitionService(model_path=str(self.model_path), labels=labels).train(samples, ids)
        elif self.model_path.exists():
            self.model_path.unlink()
        self._write_id_list(ids)
        self._write_total_user(max(labels.keys(), default=0))
        return True

    def reset(self) -> None:
        if self.data_dir.exists():
            shutil.rmtree(self.data_dir)
        if self.model_path.parent.exists():
            shutil.rmtree(self.model_path.parent)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_id_list([])
        self._write_total_user(0)
        self._write_label_map({})

    def _write_id_list(self, labels: list[int]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / "idlists.txt").write_text(
            "".join(f"{label}\n" for label in labels),
            encoding="utf-8",
        )

    def _write_total_user(self, total: int) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / "totalUser.txt").write_text(str(total), encoding="utf-8")

    def _write_label_map(self, labels: dict[int, str]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / "userdic.txt").write_text(str(labels) if labels else "", encoding="utf-8")
