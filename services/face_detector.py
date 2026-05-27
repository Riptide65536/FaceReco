from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class FaceDetection:
    bbox: tuple[int, int, int, int]
    score: Optional[float] = None
    kps: Optional["np.ndarray"] = None


class BaseFaceDetector(ABC):
    @abstractmethod
    def detect(self, frame: "np.ndarray") -> list[FaceDetection]:
        raise NotImplementedError


def _to_python(value: Any):
    if value is None:
        return None
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


class YOLOFaceDetector(BaseFaceDetector):
    def __init__(
        self,
        model_path: str | Path,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        imgsz: int = 640,
        device: str | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise RuntimeError(f"YOLO face model is missing: {self.model_path}")

        try:
            from ultralytics import YOLO  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "YOLO face detector is unavailable. Install ultralytics>=8.0.0."
            ) from exc

        self.conf_threshold = float(conf_threshold)
        self.iou_threshold = float(iou_threshold)
        self.imgsz = max(160, int(imgsz))
        self.device = device or None
        self._model = YOLO(str(self.model_path))

    def detect(self, frame: "np.ndarray") -> list[FaceDetection]:
        results = self._model.predict(
            source=frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            imgsz=self.imgsz,
            device=self.device,
            verbose=False,
        )
        if not results:
            return []

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        xyxy_list = _to_python(getattr(boxes, "xyxy", None)) or []
        conf_list = _to_python(getattr(boxes, "conf", None)) or []
        keypoints = getattr(result, "keypoints", None)
        kps_list = _to_python(getattr(keypoints, "xy", None)) or []

        detections: list[FaceDetection] = []
        for idx, coords in enumerate(xyxy_list):
            if coords is None or len(coords) < 4:
                continue
            x1, y1, x2, y2 = [int(round(float(v))) for v in coords[:4]]
            w = max(0, x2 - x1)
            h = max(0, y2 - y1)
            if w == 0 or h == 0:
                continue

            score = None
            if idx < len(conf_list):
                try:
                    score = float(conf_list[idx])
                except Exception:
                    score = None

            kps_np = None
            if idx < len(kps_list):
                try:
                    import numpy as np

                    parsed = np.asarray(kps_list[idx], dtype="float32")
                    if parsed.ndim == 2 and parsed.shape[1] >= 2:
                        kps_np = parsed[:, :2]
                except Exception:
                    kps_np = None

            detections.append(
                FaceDetection(
                    bbox=(x1, y1, w, h),
                    score=score,
                    kps=kps_np,
                )
            )

        detections.sort(key=lambda item: float(item.score or 0.0), reverse=True)
        return detections


class InsightFaceDetector(BaseFaceDetector):
    def __init__(
        self,
        providers: Optional[list[str]] = None,
        det_size: tuple[int, int] = (320, 320),
        analyzer: Any | None = None,
        model_name: str = "buffalo_l",
    ) -> None:
        if analyzer is None:
            try:
                from insightface.app import FaceAnalysis  # type: ignore
            except Exception as exc:
                raise RuntimeError(
                    "InsightFace detector is unavailable. Install insightface + onnxruntime."
                ) from exc

            analyzer = FaceAnalysis(
                name=model_name,
                providers=list(providers or ["CPUExecutionProvider"]),
                allowed_modules=["detection"],
            )
            analyzer.prepare(ctx_id=-1, det_size=det_size)

        self._analyzer = analyzer

    def detect(self, frame: "np.ndarray") -> list[FaceDetection]:
        faces = self._analyzer.get(frame)
        detections: list[FaceDetection] = []
        for face in faces:
            bbox_raw = getattr(face, "bbox", None)
            if bbox_raw is None or len(bbox_raw) < 4:
                continue
            x1, y1, x2, y2 = [int(round(float(v))) for v in bbox_raw[:4]]
            w = max(0, x2 - x1)
            h = max(0, y2 - y1)
            if w == 0 or h == 0:
                continue

            score = None
            det_score = getattr(face, "det_score", None)
            if det_score is not None:
                try:
                    score = float(det_score)
                except Exception:
                    score = None

            kps_np = None
            kps_raw = getattr(face, "kps", None)
            if kps_raw is not None:
                try:
                    import numpy as np

                    parsed = np.asarray(kps_raw, dtype="float32")
                    if parsed.ndim == 2 and parsed.shape[1] >= 2:
                        kps_np = parsed[:, :2]
                except Exception:
                    kps_np = None

            detections.append(
                FaceDetection(
                    bbox=(x1, y1, w, h),
                    score=score,
                    kps=kps_np,
                )
            )
        return detections
