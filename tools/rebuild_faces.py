from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)


def load_userdic() -> dict[int, str]:
    path = ROOT / "config" / "userdic.txt"
    if not path.exists() or path.stat().st_size == 0:
        return {}
    return {int(k): str(v) for k, v in ast.literal_eval(path.read_text(encoding="utf-8")).items()}


def save_config(userdic: dict[int, str], labels: list[int]) -> None:
    config = ROOT / "config"
    config.mkdir(exist_ok=True)
    (config / "userdic.txt").write_text(str(userdic) if userdic else "", encoding="utf-8")
    (config / "idlists.txt").write_text("".join(f"{label}\n" for label in labels), encoding="utf-8")
    (config / "totalUser.txt").write_text(str(max(userdic.keys(), default=0)), encoding="utf-8")


def collect(userdic: dict[int, str]) -> tuple[list[np.ndarray], list[int]]:
    detector = cv2.CascadeClassifier(str(ROOT / "attachment" / "haarcascade_frontalface_default.xml"))
    samples: list[np.ndarray] = []
    labels: list[int] = []
    for label, name in sorted(userdic.items()):
        folder = ROOT / "data" / name
        if not folder.is_dir():
            print(f"skip missing folder: {folder}")
            continue
        for image_path in folder.glob("*.jpg"):
            image = Image.open(image_path).convert("L")
            gray = np.array(image)
            faces = detector.detectMultiScale(gray)
            if len(faces) == 0:
                samples.append(gray)
                labels.append(label)
                continue
            for x, y, w, h in faces:
                samples.append(gray[y:y + h, x:x + w])
                labels.append(label)
    return samples, labels


def main() -> int:
    userdic = load_userdic()
    samples, labels = collect(userdic)
    model = ROOT / "model" / "model.yml"
    model.parent.mkdir(exist_ok=True)

    if not samples:
        if model.exists():
            model.unlink()
        save_config(userdic, [])
        print("No face samples found. Removed model.yml.")
        return 1

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(samples, np.array(labels))
    recognizer.write(str(model))
    save_config(userdic, labels)
    print(f"Rebuilt model: {len(samples)} samples, labels={sorted(set(labels))}")
    print(f"userdic={userdic}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
