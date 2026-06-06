from __future__ import annotations

import datetime as dt
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from paths import BASE_DIR
from services.emotion_service import EmotionRecognitionService


DISPLAY_MODES = {
    0: "\u4eba\u8138\u8bc6\u522b\u6a21\u5f0f",
    1: "\u4eba\u8138\u68c0\u6d4b\u6a21\u5f0f",
    2: "\u7eaf\u663e\u793a\u6a21\u5f0f",
}


def normalize_source(value: Any) -> Any:
    if value is None:
        return 0
    text = str(value).strip()
    if text == "":
        return 0
    aliases = {"test", "测试视频", "sample", "demo"}
    if text.lower() in aliases:
        candidates = sorted(BASE_DIR.glob("*.flv")) + sorted(BASE_DIR.glob("*.mp4"))
        return str(candidates[0]) if candidates else 0
    if text.isdigit():
        return int(text)
    return text


# ──────────────────────────────────────────────────────────────────────────────
# [优化] 预编译 CJK 字符范围判断，避免每帧重复构造判断逻辑
# ──────────────────────────────────────────────────────────────────────────────
def _has_cjk(text: str) -> bool:
    """判断字符串中是否含有需要 PIL 渲染的非 ASCII 字符（中文等）。"""
    return any(ord(c) > 127 for c in text)


_WEB_INFERENCE_SEMAPHORE = threading.Semaphore(max(1, int(os.getenv("FACE_RECO_WEB_INFER_WORKERS", "1"))))

class WebCameraSlot:
    def __init__(self, slot: int, source: Any, name: str, display_mode: int, app_service) -> None:
        self.slot = int(slot)
        self.source = normalize_source(source)
        self.name = str(name or f"监控点 {slot}").strip()
        self.display_mode = int(display_mode)
        self.app_service = app_service
        self._condition = threading.Condition()
        self._latest_jpeg: bytes | None = None
        self._latest_meta: dict[str, Any] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._cap: cv2.VideoCapture | None = None
        self._emotion = None
        self._face_counts: dict[tuple[str, str], int] = {}
        self._last_saved_at: dict[str, float] = {}
        self._stable_predictions: list[dict[str, Any]] = []
        self._model_mtime = 0.0
        self._last_track_submit_at = 0.0
        self._fast_track_gap = max(0.03, float(os.getenv("FACE_RECO_WEB_FAST_TRACK_GAP", "0.08")))
        self._emotion_cache: dict[str, dict[str, Any]] = {}
        self._emotion_cache_ttl = max(0.5, float(os.getenv("FACE_RECO_WEB_EMOTION_TTL", "2.5")))
        self._emotion_min_gap = max(0.05, float(os.getenv("FACE_RECO_WEB_EMOTION_GAP", "0.45")))
        self._last_emotion_submit_at = 0.0
        self._emotion_future_name = ""
        self._font = self._load_font(24)
        self._analysis_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"web-recog-{self.slot}")
        self._track_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"web-track-{self.slot}")
        self._emotion_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"web-emotion-{self.slot}")
        self._analysis_future: Future | None = None
        self._track_future: Future | None = None
        self._emotion_future: Future | None = None
        self._label_min_confidence = max(0.0, min(100.0, float(os.getenv("FACE_RECO_WEB_LABEL_MIN_CONF", "78"))))
        self._debug_predictions = os.getenv("FACE_RECO_WEB_DEBUG", "0") == "1"
        # [优化] 预判断监控点名称是否含 CJK，避免每帧重复扫描
        self._name_has_cjk: bool = _has_cjk(self.name)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name=f"web-camera-{self.slot}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.8)
        try:
            self._analysis_pool.shutdown(wait=False)
        except Exception:
            pass
        try:
            self._track_pool.shutdown(wait=False)
        except Exception:
            pass
        try:
            self._emotion_pool.shutdown(wait=False)
        except Exception:
            pass

    def snapshot(self) -> bytes | None:
        with self._condition:
            return self._latest_jpeg

    def wait_frame(self, timeout: float = 2.0) -> bytes | None:
        with self._condition:
            if self._latest_jpeg is None:
                self._condition.wait(timeout=timeout)
            return self._latest_jpeg

    def status(self) -> dict[str, Any]:
        with self._condition:
            meta = dict(self._latest_meta)
        return {
            "slot": self.slot,
            "name": self.name,
            "source": str(self.source),
            "displayMode": self.display_mode,
            "displayModeText": DISPLAY_MODES.get(self.display_mode, "未知模式"),
            "running": self._running,
            "meta": meta,
        }

    def _loop(self) -> None:
        self._cap = cv2.VideoCapture(self.source)
        try:
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        if not self._cap.isOpened():
            self._publish_placeholder("视频源无法打开")
            self._running = False
            return

        face_service = None
        if self.app_service.pipeline.ensure_face_service_ready():
            face_service = self.app_service.pipeline.face_service
            if face_service is not None:
                face_service.labels = dict(self.app_service.state.user_dic)
                if hasattr(face_service, "set_realtime_mode"):
                    face_service.set_realtime_mode(self.app_service.state.realtime_mode)
                if self.display_mode == 0 and self.app_service.data_repo.model_exists():
                    try:
                        face_service.load_model()
                        self._model_mtime = self._current_model_mtime()
                    except Exception:
                        pass
        try:
            self._emotion = EmotionRecognitionService()
        except Exception:
            self._emotion = None

        last_analysis = 0.0
        last_predictions: list[dict[str, Any]] = []
        frame_index = 0
        last_emit = 0.0
        fps = 0.0

        # [优化] 预判断标题栏是否需要 PIL 渲染，只算一次
        title_needs_pil = _has_cjk(self.name)

        while self._running and self._cap is not None and self._cap.isOpened():
            ok, frame = self._cap.read()
            if not ok:
                break
            frame_index += 1
            now = time.monotonic()
            target_fps = self._target_fps()
            if target_fps > 0 and now - last_emit < (1.0 / target_fps):
                continue
            if last_emit > 0:
                instant = 1.0 / max(1e-6, now - last_emit)
                fps = instant if fps <= 0 else (fps * 0.82 + instant * 0.18)
            last_emit = now

            frame = cv2.resize(frame, (960, 540))

            if self._analysis_future is not None and self._analysis_future.done():
                try:
                    last_predictions = self._stabilize_predictions(self._analysis_future.result())
                except Exception:
                    last_predictions = []
                finally:
                    self._analysis_future = None

            if self._track_future is not None and self._track_future.done():
                try:
                    tracked_boxes = self._track_future.result()
                    last_predictions = self._merge_tracked_boxes(last_predictions, tracked_boxes)
                except Exception:
                    pass
                finally:
                    self._track_future = None

            self._collect_emotion_result()

            has_detector = face_service is not None or getattr(self.app_service.pipeline, "_fallback_detector", None) is not None
            should_analyze = (
                has_detector
                and self.display_mode in (0, 1)
                and self._analysis_future is None
                and now - last_analysis >= self._analysis_gap()
            )
            if should_analyze:
                self._analysis_future = self._analysis_pool.submit(
                    self._analyze_frame,
                    face_service,
                    frame.copy(),
                    frame_index,
                )
                last_analysis = now

            if self.display_mode == 0:
                self._submit_track_task(frame, now)
                self._submit_emotion_tasks(frame, last_predictions, now)
                last_predictions = self._apply_cached_emotions(last_predictions, now)

            display = self._draw_overlay(frame, last_predictions, fps, title_needs_pil)
            ok, jpeg = cv2.imencode(".jpg", display, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
            if ok:
                self._publish(
                    jpeg.tobytes(),
                    {
                        "fps": round(fps, 1),
                        "people": [
                            self._resolve_display_name(item)
                            for item in last_predictions
                            if self._resolve_display_name(item)
                        ],
                        "updatedAt": dt.datetime.now().strftime("%H:%M:%S"),
                    },
                )
        self._running = False
        self._publish_placeholder("无信号")

    def _target_fps(self) -> float:
        mode = str(self.app_service.state.realtime_mode or "balanced")
        if self.display_mode == 0:
            defaults = {"realtime": 20.0, "balanced": 16.0, "accurate": 12.0}
        else:
            defaults = {"realtime": 24.0, "balanced": 18.0, "accurate": 14.0}
        value = defaults.get(mode, 18.0)
        env_name = {
            "realtime": "FACE_RECO_UI_FPS_REALTIME",
            "balanced": "FACE_RECO_UI_FPS_BALANCED",
            "accurate": "FACE_RECO_UI_FPS_ACCURATE",
        }.get(mode)
        if env_name:
            try:
                value = float(os.getenv(env_name, value))
            except Exception:
                pass
        return max(0.0, value)

    def _analysis_gap(self) -> float:
        mode = str(self.app_service.state.realtime_mode or "balanced")
        if self.display_mode == 0:
            defaults = {"realtime": 0.35, "balanced": 0.65, "accurate": 0.95}
            value = defaults.get(mode, 0.65)
            try:
                return max(0.15, float(os.getenv("FACE_RECO_WEB_RECOG_GAP", value)))
            except Exception:
                return value
        return {"realtime": 0.18, "balanced": 0.34, "accurate": 0.55}.get(mode, 0.34)

    # [优化] 增加 frame_index 参数，透传给 face_service 作为轻量缓存 key
    def _analyze_frame(
        self,
        face_service,
        frame: np.ndarray,
        frame_index: int = 0,
    ) -> list[dict[str, Any]]:
        try:
            with _WEB_INFERENCE_SEMAPHORE:
                analysis_frame, scale = self._prepare_analysis_frame(frame)
                if self.display_mode == 1:
                    return self._detect_only(face_service, analysis_frame, scale)
                try:
                    self._ensure_latest_model(face_service)
                    predictions = face_service.recognize_frame(analysis_frame, cache_key=str(frame_index)) if face_service is not None else []
                except Exception as exc:
                    print(f"web recognize failed on slot {self.slot}: {exc}")
                    predictions = []
                if not predictions:
                    return self._detect_only(face_service, analysis_frame, scale)
                if self._debug_predictions:
                    print(
                        "web predictions",
                        [
                            {
                                "label": item.get("label"),
                                "name": item.get("name"),
                                "confidence": item.get("confidence"),
                                "similarity": item.get("similarity"),
                            }
                            for item in predictions
                        ],
                    )
                output: list[dict[str, Any]] = []
                for pred in predictions:
                    pred = dict(pred)
                    pred["bbox"] = self._scale_bbox(tuple(map(int, pred.get("bbox", (0, 0, 0, 0)))), scale)
                    output.append(pred)
                return output
        except Exception as exc:
            print(f"web analysis failed on slot {self.slot}: {exc}")
            return []

    def _detect_only(self, face_service, analysis_frame: np.ndarray, scale: float) -> list[dict[str, Any]]:
        boxes = []
        if face_service is not None:
            try:
                boxes = face_service.detect_faces(analysis_frame)
            except Exception as exc:
                print(f"web detect failed on slot {self.slot}: {exc}")
                boxes = []
        if not boxes:
            fallback = getattr(self.app_service.pipeline, "_fallback_detector", None)
            if fallback is not None:
                try:
                    gray = cv2.cvtColor(analysis_frame, cv2.COLOR_BGR2GRAY)
                    boxes = fallback.detectMultiScale(gray, 1.3, 5)
                except Exception as exc:
                    print(f"web fallback detect failed on slot {self.slot}: {exc}")
                    boxes = []
        return [
            {"bbox": self._scale_bbox(tuple(map(int, box)), scale), "name": ""}
            for box in boxes
        ]

    def _prepare_analysis_frame(self, frame: np.ndarray) -> tuple[np.ndarray, float]:
        width = frame.shape[1]
        if self.display_mode == 0:
            target_width = max(320, min(640, int(os.getenv("FACE_RECO_WEB_RECOG_WIDTH", "416"))))
        else:
            target_width = 640
        if width <= target_width:
            return frame, 1.0
        scale = width / float(target_width)
        target_height = max(1, int(frame.shape[0] / scale))
        return cv2.resize(frame, (target_width, target_height)), scale

    @staticmethod
    def _scale_bbox(bbox: tuple[int, int, int, int], scale: float) -> tuple[int, int, int, int]:
        if scale == 1.0:
            return bbox
        x, y, w, h = bbox
        return int(x * scale), int(y * scale), int(w * scale), int(h * scale)

    def _current_model_mtime(self) -> float:
        try:
            return float(self.app_service.data_repo.model_file_path().stat().st_mtime)
        except Exception:
            return 0.0

    def _ensure_latest_model(self, face_service) -> None:
        if face_service is None or not self.app_service.data_repo.model_exists():
            return
        face_service.labels = dict(self.app_service.state.user_dic)
        mtime = self._current_model_mtime()
        if mtime <= 0.0 or mtime == self._model_mtime:
            return
        try:
            face_service.load_model()
            self._model_mtime = mtime
            self._stable_predictions = []
        except Exception as exc:
            print(f"web model reload failed on slot {self.slot}: {exc}")

    def _resolve_display_name(self, pred: dict[str, Any]) -> str:
        name = str(pred.get("name") or "").strip()
        score = self._prediction_score(pred)
        if score is not None and score < self._label_min_confidence:
            return ""
        if name and name.lower() != "unknown" and name.replace("?", "").strip():
            return name
        label = pred.get("label")
        if label is None:
            return ""
        if score is None or score < self._label_min_confidence:
            return ""
        try:
            resolved = str(self.app_service.state.user_dic.get(int(label), "")).strip()
            return resolved if resolved.replace("?", "").strip() else ""
        except Exception:
            return ""

    @staticmethod
    def _prediction_score(pred: dict[str, Any]) -> float | None:
        confidence = pred.get("confidence")
        similarity = pred.get("similarity")
        try:
            if confidence is not None:
                return float(confidence)
            if similarity is not None:
                value = float(similarity)
                return value * 100.0 if value <= 1.5 else value
        except Exception:
            return None
        return None

    @staticmethod
    def _bbox_center(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
        x, y, w, h = bbox
        return float(x) + float(w) / 2.0, float(y) + float(h) / 2.0

    @staticmethod
    def _bbox_match_score(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax, ay = WebCameraSlot._bbox_center(a)
        bx, by = WebCameraSlot._bbox_center(b)
        aw, ah = max(1.0, float(a[2])), max(1.0, float(a[3]))
        bw, bh = max(1.0, float(b[2])), max(1.0, float(b[3]))
        distance = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
        scale = max(aw, ah, bw, bh, 1.0)
        return distance / scale

    def _stabilize_predictions(self, predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        previous = [dict(item) for item in self._stable_predictions]
        stabilized: list[dict[str, Any]] = []
        for pred in predictions:
            current = dict(pred)
            current_bbox = tuple(map(int, current.get("bbox", (0, 0, 0, 0))))
            current_name = self._resolve_display_name(current)
            best_prev = None
            best_score = 999.0
            for old in previous:
                old_name = self._resolve_display_name(old)
                if not old_name:
                    continue
                old_bbox = tuple(map(int, old.get("bbox", (0, 0, 0, 0))))
                score = self._bbox_match_score(current_bbox, old_bbox)
                if score < best_score:
                    best_score = score
                    best_prev = old
            if best_prev is not None and best_score <= 0.85:
                if not current_name:
                    current["name"] = self._resolve_display_name(best_prev)
                    current["label"] = best_prev.get("label", current.get("label"))
                    current["confidence"] = best_prev.get("confidence", current.get("confidence"))
                    current["similarity"] = best_prev.get("similarity", current.get("similarity"))
                if not current.get("emotion") and best_prev.get("emotion"):
                    current["emotion"] = best_prev.get("emotion")
            stabilized.append(current)
        self._stable_predictions = [dict(item) for item in stabilized]
        return stabilized

    def _submit_track_task(self, frame: np.ndarray, now: float) -> None:
        if now - self._last_track_submit_at < self._fast_track_gap:
            return
        if self._track_future is not None:
            return
        fallback = getattr(self.app_service.pipeline, "_fallback_detector", None)
        if fallback is None:
            return
        self._last_track_submit_at = now
        self._track_future = self._track_pool.submit(self._detect_track_boxes, frame.copy())

    def _detect_track_boxes(self, frame: np.ndarray) -> list[tuple[int, int, int, int]]:
        fallback = getattr(self.app_service.pipeline, "_fallback_detector", None)
        if fallback is None:
            return []
        try:
            width = frame.shape[1]
            target_width = max(240, min(640, int(os.getenv("FACE_RECO_WEB_TRACK_WIDTH", "480"))))
            if width > target_width:
                scale = width / float(target_width)
                small_h = max(1, int(frame.shape[0] / scale))
                small = cv2.resize(frame, (target_width, small_h))
            else:
                scale = 1.0
                small = frame
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            boxes = fallback.detectMultiScale(gray, 1.2, 4)
        except Exception:
            return []
        if boxes is None or len(boxes) == 0:
            return []
        return [self._scale_bbox(tuple(map(int, box)), scale) for box in boxes]

    def _merge_tracked_boxes(
        self,
        previous: list[dict[str, Any]],
        boxes: list[tuple[int, int, int, int]],
    ) -> list[dict[str, Any]]:
        if not boxes:
            return previous
        merged: list[dict[str, Any]] = []
        used_prev: set[int] = set()
        for box in boxes:
            best_idx = -1
            best_score = 999.0
            for idx, old in enumerate(previous):
                if idx in used_prev:
                    continue
                old_box = tuple(map(int, old.get("bbox", (0, 0, 0, 0))))
                score = self._bbox_match_score(tuple(map(int, box)), old_box)
                if score < best_score:
                    best_score = score
                    best_idx = idx
            if best_idx >= 0 and best_score <= 1.15:
                used_prev.add(best_idx)
                item = dict(previous[best_idx])
                item["bbox"] = tuple(map(int, box))
                item["tracked"] = True
            else:
                item = {"bbox": tuple(map(int, box)), "name": ""}
            merged.append(item)
        self._stable_predictions = [dict(item) for item in merged]
        return merged

    def _collect_emotion_result(self) -> None:
        if self._emotion_future is None or not self._emotion_future.done():
            return
        try:
            name, emotion, ts = self._emotion_future.result()
            if name:
                self._emotion_cache[name] = {"emotion": emotion, "ts": float(ts)}
        except Exception:
            pass
        finally:
            self._emotion_future = None
            self._emotion_future_name = ""

    def _submit_emotion_tasks(self, frame: np.ndarray, predictions: list[dict[str, Any]], now: float) -> None:
        if self._emotion is None or self._emotion_future is not None:
            return
        if now - self._last_emotion_submit_at < self._emotion_min_gap:
            return
        gray = None
        for pred in predictions:
            name = self._resolve_display_name(pred)
            if not name:
                continue
            cached = self._emotion_cache.get(name)
            if cached and now - float(cached.get("ts", 0.0)) <= self._emotion_cache_ttl:
                continue
            x, y, w, h = tuple(map(int, pred.get("bbox", (0, 0, 0, 0))))
            if gray is None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            crop = gray[max(0, y) : max(0, y + h), max(0, x) : max(0, x + w)]
            if crop.size == 0:
                continue
            face_copy = np.ascontiguousarray(crop.copy())
            self._last_emotion_submit_at = now
            self._emotion_future_name = name
            self._emotion_future = self._emotion_pool.submit(self._predict_emotion, name, face_copy, now)
            return

    def _predict_emotion(self, name: str, face_gray: np.ndarray, ts: float) -> tuple[str, str, float]:
        emotion = "\u4e2d\u6027"
        if self._emotion is not None:
            try:
                emotion, _ = self._emotion.predict(face_gray)
            except Exception:
                emotion = "\u4e2d\u6027"
        return name, emotion, ts

    def _apply_cached_emotions(self, predictions: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for pred in predictions:
            item = dict(pred)
            name = self._resolve_display_name(item)
            if not name:
                output.append(item)
                continue
            item["name"] = name
            cached = self._emotion_cache.get(name)
            emotion = "\u4e2d\u6027"
            if cached and now - float(cached.get("ts", 0.0)) <= self._emotion_cache_ttl:
                emotion = str(cached.get("emotion") or emotion)
            item["emotion"] = emotion
            try:
                self._persist_known_face(name, emotion)
            except Exception as exc:
                print(f"web emotion/log failed on slot {self.slot}: {exc}")
            output.append(item)
        self._stable_predictions = [dict(item) for item in output]
        return output

    def _persist_known_face(self, name: str, emotion: str) -> None:
        if not name:
            return
        key = (name, emotion)
        self._face_counts[key] = self._face_counts.get(key, 0) + 1
        if self._face_counts[key] < 5:
            return
        self._face_counts[key] = 0
        now = time.monotonic()
        if now - self._last_saved_at.get(name, 0.0) < 8.0:
            return
        self._last_saved_at[name] = now
        self._save_recognition_event(name, emotion)

    def _attach_emotion_and_persist(self, frame: np.ndarray, pred: dict[str, Any]) -> None:
        name = self._resolve_display_name(pred)
        if not name:
            return
        pred["name"] = name
        x, y, w, h = tuple(map(int, pred.get("bbox", (0, 0, 0, 0))))
        emotion = "\u4e2d\u6027"
        if self._emotion is not None:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                crop = gray[max(0, y) : max(0, y + h), max(0, x) : max(0, x + w)]
                emotion, _ = self._emotion.predict(crop)
            except Exception:
                emotion = "\u4e2d\u6027"
        pred["emotion"] = emotion
        self._persist_known_face(name, emotion)

    def _save_recognition_event(self, name: str, emotion: str) -> None:
        now_dt = dt.datetime.now().replace(microsecond=0)
        state = self.app_service.state
        custom_label = state.active_custom_attendance_label()
        if not custom_label:
            self.app_service.sql_repo.save_recognition_event(name, self.name, now_dt, emotion=emotion)
            return
        if not state.try_mark_custom_attendance_recorded(name):
            return
        daily_types = set(self.app_service.sql_repo.get_daily_attendance_types(name, now_dt))
        if not daily_types.intersection({"上班打卡", "下班打卡", "外出登记"}):
            self.app_service.sql_repo.save_recognition_event(name, self.name, now_dt, emotion=emotion)
        ok = self.app_service.sql_repo.save_recognition_event(
            name,
            self.name,
            now_dt,
            emotion=emotion,
            attendance_type=custom_label,
        )
        if not ok:
            state.unmark_custom_attendance_recorded(name)

    # [优化] 增加 title_needs_pil 参数，避免每帧重新扫描标题字符
    def _draw_overlay(
        self,
        frame: np.ndarray,
        predictions: list[dict[str, Any]],
        fps: float,
        title_needs_pil: bool = True,
    ) -> np.ndarray:
        labels: list[tuple[str, tuple[int, int]]] = []
        # [优化] 提前判断本次预测结果中是否有需要 PIL 渲染的标签
        needs_pil = title_needs_pil

        for pred in predictions:
            x, y, w, h = tuple(map(int, pred.get("bbox", (0, 0, 0, 0))))
            cv2.rectangle(frame, (x, y), (x + w, y + h), (23, 214, 196), 2)
            if self.display_mode == 1:
                continue
            name = self._resolve_display_name(pred)
            emotion = str(pred.get("emotion") or "").strip()
            if not name:
                continue
            label = name if not emotion else f"{name} | {emotion}"
            # [优化] 只要有一个标签含 CJK 就标记需要 PIL
            if not needs_pil and _has_cjk(label):
                needs_pil = True
            labels.append((label, (x + 5, max(24, y - 30))))

        cv2.rectangle(frame, (0, 0), (frame.shape[1], 36), (8, 15, 25), -1)
        labels.append((self.name, (12, 7)))
        if self.app_service.state.show_fps_overlay:
            cv2.putText(
                frame,
                f"FPS {fps:.1f}",
                (frame.shape[1] - 112, 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (70, 230, 143),
                2,
            )

        # [优化] 无 CJK 字符时直接用 cv2.putText，完全跳过 PIL 双向转换（节省 3~8ms/帧）
        if not needs_pil:
            for text, (x, y) in labels:
                safe_text = str(text).replace("???", "").strip()
                if not safe_text:
                    continue
                cv2.putText(frame, safe_text, (x, y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (236, 244, 255), 1)
            return frame

        return self._draw_text_labels(frame, labels)

    @staticmethod
    def _load_font(size: int):
        candidates = [
            Path(os.getenv("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc",
            Path(os.getenv("WINDIR", "C:/Windows")) / "Fonts" / "simhei.ttf",
        ]
        for path in candidates:
            try:
                if path.exists():
                    return ImageFont.truetype(str(path), size)
            except Exception:
                pass
        return ImageFont.load_default()

    def _draw_text_labels(self, frame: np.ndarray, labels: list[tuple[str, tuple[int, int]]]) -> np.ndarray:
        if not labels:
            return frame
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(image)
        for text, (x, y) in labels:
            safe_text = str(text).replace("???", "").strip()
            if not safe_text:
                continue
            bbox = draw.textbbox((x, y), safe_text, font=self._font)
            draw.rectangle((bbox[0] - 5, bbox[1] - 3, bbox[2] + 5, bbox[3] + 3), fill=(8, 15, 25))
            draw.text((x, y), safe_text, font=self._font, fill=(236, 244, 255))
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    def _publish(self, data: bytes, meta: dict[str, Any] | None = None) -> None:
        with self._condition:
            self._latest_jpeg = data
            self._latest_meta = meta or {}
            self._condition.notify_all()

    def _publish_placeholder(self, text: str) -> None:
        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        frame[:] = (13, 20, 31)
        cv2.putText(frame, str(text), (360, 270), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (166, 184, 205), 2)
        ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if ok:
            self._publish(jpeg.tobytes(), {"status": text})


class WebCameraManager:
    def __init__(self, app_service) -> None:
        self.app_service = app_service
        self._slots: dict[int, WebCameraSlot] = {}
        self._lock = threading.RLock()

    def start(self, slot: int, source: Any, name: str, display_mode: int) -> WebCameraSlot:
        with self._lock:
            self.stop(slot)
            cam = WebCameraSlot(slot, source, name, display_mode, self.app_service)
            self._slots[int(slot)] = cam
            cam.start()
            return cam

    def stop(self, slot: int) -> None:
        with self._lock:
            cam = self._slots.pop(int(slot), None)
        if cam is not None:
            cam.stop()

    def stop_matching_source(self, source: Any) -> list[dict[str, Any]]:
        normalized = str(normalize_source(source))
        snapshots: list[dict[str, Any]] = []
        with self._lock:
            slots = [
                slot
                for slot, cam in self._slots.items()
                if str(normalize_source(cam.source)) == normalized
            ]
            for slot in slots:
                cam = self._slots.pop(slot, None)
                if cam is None:
                    continue
                snapshots.append(
                    {
                        "slot": cam.slot,
                        "source": cam.source,
                        "name": cam.name,
                        "displayMode": cam.display_mode,
                    }
                )
                cam.stop()
        return snapshots

    def restore_snapshots(self, snapshots: list[dict[str, Any]]) -> None:
        for item in snapshots:
            try:
                self.start(
                    int(item.get("slot", 0)),
                    item.get("source", 0),
                    str(item.get("name") or ""),
                    int(item.get("displayMode", 0)),
                )
            except Exception as exc:
                print(f"web restore camera failed: {exc}")

    def stop_all(self) -> None:
        with self._lock:
            slots = list(self._slots.keys())
        for slot in slots:
            self.stop(slot)

    def get(self, slot: int) -> WebCameraSlot | None:
        with self._lock:
            return self._slots.get(int(slot))

    def statuses(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._slots[i].status() for i in sorted(self._slots)]
