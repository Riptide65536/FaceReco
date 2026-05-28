from __future__ import annotations

from collections import deque
import os
from pathlib import Path
import sys

import numpy as np


class EmotionRecognitionService:
    """Keras emotion classifier with small multi-frame smoothing buffer."""

    EMOTIONS = [
        "\u9ad8\u5174",
        "\u60b2\u4f24",
        "\u6124\u6012",
        "\u60ca\u8bb6",
        "\u6050\u60e7",
        "\u538c\u6076",
        "\u4e2d\u6027",
    ]
    _NEUTRAL = "\u4e2d\u6027"
    _LOGGED_STATUS_KEYS: set[str] = set()
    _DLL_DIR_HANDLES: list[object] = []

    def __init__(self, model_path: str = "model/emotion_model.h5", window_size: int = 5) -> None:
        self.model_path = Path(model_path)
        self.window: deque[np.ndarray] = deque(maxlen=window_size)
        self.model = None
        self.model_format = "missing"
        self.runtime_device = "CPU"
        self.tf_gpu_devices: list[str] = []
        if not self.model_path.exists():
            self._log_status(
                f"emotion model: missing ({self.model_path}) fallback={self._NEUTRAL}"
            )
            return
        try:
            self.model = self._load_model()
        except Exception as exc:
            self._log_status(f"emotion model: failed ({self.model_path}) error={exc}")
            raise

    def _load_model(self):
        self._ensure_windows_cuda_runtime_path()
        try:
            import tensorflow as tf
            from tensorflow.keras.models import Sequential, load_model
            from tensorflow.keras.layers import Conv2D, Dense, Dropout, Flatten, MaxPooling2D
        except ImportError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError("TensorFlow/Keras is required for emotion recognition.") from exc

        self.tf_gpu_devices = self._detect_tf_gpu_devices(tf)
        self.runtime_device = "GPU" if self.tf_gpu_devices else "CPU"

        try:
            model = load_model(str(self.model_path), compile=False)
            self.model_format = "keras_h5"
            self._log_loaded_status()
            return model
        except ValueError as exc:
            if "No model config found" not in str(exc):
                raise

        # Some public FER models are distributed as H5 weights only.
        model = Sequential(
            [
                Conv2D(32, kernel_size=(3, 3), activation="relu", input_shape=(48, 48, 1), name="conv2d"),
                Conv2D(64, kernel_size=(3, 3), activation="relu", name="conv2d_1"),
                MaxPooling2D(pool_size=(2, 2), name="max_pooling2d"),
                Dropout(0.25, name="dropout"),
                Conv2D(128, kernel_size=(3, 3), activation="relu", name="conv2d_2"),
                MaxPooling2D(pool_size=(2, 2), name="max_pooling2d_1"),
                Conv2D(128, kernel_size=(3, 3), activation="relu", name="conv2d_3"),
                MaxPooling2D(pool_size=(2, 2), name="max_pooling2d_2"),
                Dropout(0.25, name="dropout_1"),
                Flatten(name="flatten"),
                Dense(1024, activation="relu", name="dense"),
                Dropout(0.5, name="dropout_2"),
                Dense(7, activation="softmax", name="dense_1"),
            ]
        )
        model.load_weights(str(self.model_path))
        self.model_format = "weights_only_h5"
        self._log_loaded_status()
        return model

    def predict(self, face_gray: np.ndarray) -> tuple[str, float]:
        if self.model is None:
            return self._NEUTRAL, 0.0
        prepared = self._preprocess(face_gray)
        probs = np.asarray(self.model.predict(prepared, verbose=0)[0], dtype="float32")
        if probs.ndim != 1 or probs.size != len(self.EMOTIONS):
            return self._NEUTRAL, 0.0
        self.window.append(probs)
        fused = np.mean(np.stack(tuple(self.window), axis=0), axis=0)
        index = int(np.argmax(fused))
        return self.EMOTIONS[index], float(fused[index])

    @staticmethod
    def _preprocess(face_gray: np.ndarray) -> np.ndarray:
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("OpenCV is required for emotion preprocessing.") from exc
        face = cv2.resize(face_gray, (48, 48)).astype("float32") / 255.0
        return face.reshape(1, 48, 48, 1)

    @staticmethod
    def _detect_tf_gpu_devices(tf_module) -> list[str]:
        config = getattr(tf_module, "config", None)
        if config is None or not hasattr(config, "list_physical_devices"):
            return []
        try:
            devices = config.list_physical_devices("GPU")
        except Exception:
            return []
        return [getattr(device, "name", str(device)) for device in devices]

    @classmethod
    def _ensure_windows_cuda_runtime_path(cls) -> None:
        if os.name != "nt":
            return
        library_bin = Path(sys.prefix) / "Library" / "bin"
        if not library_bin.exists():
            return
        library_bin_text = str(library_bin)
        current_path = os.environ.get("PATH", "")
        if library_bin_text.lower() not in current_path.lower():
            os.environ["PATH"] = library_bin_text + os.pathsep + current_path
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is None:
            return
        try:
            cls._DLL_DIR_HANDLES.append(add_dll_directory(library_bin_text))
        except (FileNotFoundError, OSError):
            return

    def _log_loaded_status(self) -> None:
        self._log_status(
            "emotion model: loaded "
            f"({self.model_path}) "
            f"format={self.model_format} "
            f"device={self.runtime_device} "
            f"tf_gpus={len(self.tf_gpu_devices)}"
        )

    def _log_status(self, message: str) -> None:
        try:
            path_key = str(self.model_path.resolve())
        except Exception:
            path_key = str(self.model_path)
        log_key = f"{path_key}|{message}"
        if log_key in self._LOGGED_STATUS_KEYS:
            return
        self._LOGGED_STATUS_KEYS.add(log_key)
        print(message)
