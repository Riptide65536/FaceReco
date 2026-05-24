from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

try:
    import numpy as np
except Exception:
    np = None

cv2 = None


def _require_cv2():
    global cv2
    if cv2 is not None:
        return cv2
    try:
        import cv2 as _cv2  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"OpenCV is required: {exc}")
    cv2 = _cv2
    return cv2


ROOT = Path(__file__).resolve().parents[1]
CASCADE_PATH = ROOT / "assets" / "attachment" / "haarcascade_frontalface_default.xml"
MODEL_PATH = ROOT / "model" / "model.yml"
DEFAULT_SOURCE = ROOT / "1 Danny MacAskill’s Wee Day Out.flv"


def _parse_source(value: str) -> Any:
    if value.isdigit():
        return int(value)
    return value


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if np is not None:
        return float(np.percentile(np.asarray(values, dtype=np.float64), q))
    # Pure-Python fallback (linear interpolation).
    arr = sorted(float(v) for v in values)
    if len(arr) == 1:
        return arr[0]
    idx = (len(arr) - 1) * (q / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(arr) - 1)
    frac = idx - lo
    return arr[lo] * (1.0 - frac) + arr[hi] * frac


def benchmark(
    source: Any,
    frames: int,
    warmup: int,
    mode: str,
    resize_width: int = 640,
    resize_height: int = 360,
) -> int:
    cv2_local = _require_cv2()
    cap = cv2_local.VideoCapture(source)
    if not cap.isOpened():
        print(f"[ERR] cannot open source: {source}")
        return 2

    detector = cv2_local.CascadeClassifier(str(CASCADE_PATH))
    if detector.empty():
        print(f"[ERR] cannot load cascade: {CASCADE_PATH}")
        cap.release()
        return 2

    recognizer = None
    if mode in {"recognize", "recognize_emotion"}:
        if not MODEL_PATH.exists():
            print(f"[WARN] model not found ({MODEL_PATH}), fallback to detect mode.")
            mode = "detect"
        elif not hasattr(cv2_local, "face"):
            print("[WARN] opencv-contrib (cv2.face) not available, fallback to detect mode.")
            mode = "detect"
        else:
            recognizer = cv2_local.face.LBPHFaceRecognizer_create()
            recognizer.read(str(MODEL_PATH))

    emotion_service = None
    if mode == "recognize_emotion":
        try:
            from services.emotion_service import EmotionRecognitionService

            emotion_service = EmotionRecognitionService()
        except Exception as exc:
            print(f"[WARN] emotion service unavailable ({exc}), fallback to recognize mode.")
            mode = "recognize"

    latencies_ms: list[float] = []
    face_count = 0
    predict_count = 0
    emotion_count = 0
    read_fail = 0
    processed = 0

    overall_start = time.perf_counter()
    while processed < frames:
        ok, frame = cap.read()
        if not ok:
            read_fail += 1
            break

        if processed < warmup:
            processed += 1
            continue

        t0 = time.perf_counter()
        frame = cv2_local.resize(frame, (resize_width, resize_height))
        gray = cv2_local.cvtColor(frame, cv2_local.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, 1.3, 5)
        face_count += len(faces)

        if mode in {"recognize", "recognize_emotion"} and recognizer is not None:
            for (x, y, w, h) in faces:
                _id, _conf = recognizer.predict(gray[y : y + h, x : x + w])
                predict_count += 1
                if mode == "recognize_emotion" and emotion_service is not None:
                    try:
                        emotion_service.predict(gray[y : y + h, x : x + w])
                        emotion_count += 1
                    except Exception:
                        pass

        elapsed = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed)
        processed += 1

    duration = time.perf_counter() - overall_start
    cap.release()

    measured_frames = len(latencies_ms)
    if measured_frames == 0:
        print("[ERR] no measured frames. Check source/codec/camera.")
        return 2

    summary = _build_summary(
        source=source,
        mode=mode,
        measured_frames=measured_frames,
        read_fail=read_fail,
        face_count=face_count,
        predict_count=predict_count,
        emotion_count=emotion_count,
        duration=duration,
        latencies_ms=latencies_ms,
    )

    _print_summary(summary)
    return 0


def _build_summary(
    source: Any,
    mode: str,
    measured_frames: int,
    read_fail: int,
    face_count: int,
    predict_count: int,
    emotion_count: int,
    duration: float,
    latencies_ms: list[float],
) -> dict[str, Any]:
    if np is not None:
        avg_ms = float(np.mean(latencies_ms))
        max_ms = float(np.max(latencies_ms))
    else:
        avg_ms = float(sum(latencies_ms) / len(latencies_ms))
        max_ms = float(max(latencies_ms))
    p95_ms = _percentile(latencies_ms, 95)
    p99_ms = _percentile(latencies_ms, 99)
    fps = measured_frames / duration if duration > 0 else 0.0
    return {
        "source": str(source),
        "mode": mode,
        "measured_frames": measured_frames,
        "read_fail": read_fail,
        "faces_detected": face_count,
        "predict_calls": predict_count,
        "emotion_calls": emotion_count,
        "avg_latency_ms": avg_ms,
        "p95_latency_ms": p95_ms,
        "p99_latency_ms": p99_ms,
        "max_latency_ms": max_ms,
        "effective_fps": fps,
        "pass_single_response_le_1000ms": max_ms <= 1000.0,
        "duration_seconds": duration,
    }


def _print_summary(summary: dict[str, Any]) -> None:
    print("=== Performance Check ===")
    print(f"source={summary['source']}")
    print(f"mode={summary['mode']}")
    print(f"measured_frames={summary['measured_frames']}")
    print(f"read_fail={summary['read_fail']}")
    print(f"faces_detected={summary['faces_detected']}")
    print(f"predict_calls={summary['predict_calls']}")
    print(f"emotion_calls={summary['emotion_calls']}")
    print(f"avg_latency_ms={summary['avg_latency_ms']:.2f}")
    print(f"p95_latency_ms={summary['p95_latency_ms']:.2f}")
    print(f"p99_latency_ms={summary['p99_latency_ms']:.2f}")
    print(f"max_latency_ms={summary['max_latency_ms']:.2f}")
    print(f"effective_fps={summary['effective_fps']:.2f}")
    print(f"pass_single_response<=1000ms={summary['pass_single_response_le_1000ms']}")


def run_stability_check(
    source: Any,
    mode: str,
    duration_seconds: int,
    report_interval: int,
    warmup: int,
    chunk_frames: int = 120,
) -> dict[str, Any]:
    cv2_local = _require_cv2()
    """Run repeated mini-benchmarks for a time window and report stability trends."""
    start = time.time()
    next_report = start + max(1, report_interval)
    all_chunks: list[dict[str, Any]] = []
    total_frames = 0
    total_fail = 0

    while True:
        now = time.time()
        if now - start >= duration_seconds:
            break
        # One chunk per iteration, then aggregate.
        cap = cv2_local.VideoCapture(source)
        if not cap.isOpened():
            return {
                "error": f"cannot open source: {source}",
                "duration_seconds": 0,
                "chunks": [],
            }
        cap.release()

        # Reuse the existing benchmark path by running a short measurement.
        chunk_start = time.time()
        cap2 = cv2_local.VideoCapture(source)
        detector = cv2_local.CascadeClassifier(str(CASCADE_PATH))
        recognizer = None
        effective_mode = mode
        if mode in {"recognize", "recognize_emotion"} and MODEL_PATH.exists() and hasattr(cv2_local, "face"):
            recognizer = cv2_local.face.LBPHFaceRecognizer_create()
            recognizer.read(str(MODEL_PATH))
        else:
            effective_mode = "detect"
        emotion_service = None
        if mode == "recognize_emotion":
            try:
                from services.emotion_service import EmotionRecognitionService

                emotion_service = EmotionRecognitionService()
            except Exception:
                effective_mode = "recognize" if recognizer is not None else "detect"

        lat: list[float] = []
        read_fail = 0
        faces_total = 0
        pred_total = 0
        emo_total = 0
        idx = 0
        while idx < max(chunk_frames, warmup + 10):
            ok, frame = cap2.read()
            if not ok:
                read_fail += 1
                break
            if idx < warmup:
                idx += 1
                continue
            t0 = time.perf_counter()
            frame = cv2_local.resize(frame, (640, 360))
            gray = cv2_local.cvtColor(frame, cv2_local.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(gray, 1.3, 5)
            faces_total += len(faces)
            if effective_mode in {"recognize", "recognize_emotion"} and recognizer is not None:
                for (x, y, w, h) in faces:
                    recognizer.predict(gray[y : y + h, x : x + w])
                    pred_total += 1
                    if effective_mode == "recognize_emotion" and emotion_service is not None:
                        try:
                            emotion_service.predict(gray[y : y + h, x : x + w])
                            emo_total += 1
                        except Exception:
                            pass
            lat.append((time.perf_counter() - t0) * 1000.0)
            idx += 1
        cap2.release()

        if lat:
            chunk_duration = time.time() - chunk_start
            chunk_summary = _build_summary(
                source=source,
                mode=effective_mode,
                measured_frames=len(lat),
                read_fail=read_fail,
                face_count=faces_total,
                predict_count=pred_total,
                emotion_count=emo_total,
                duration=chunk_duration,
                latencies_ms=lat,
            )
            all_chunks.append(chunk_summary)
            total_frames += len(lat)
            total_fail += read_fail

        if time.time() >= next_report:
            if all_chunks:
                latest = all_chunks[-1]
                print(
                    f"[stability] t+{int(time.time()-start)}s "
                    f"fps={latest['effective_fps']:.2f} "
                    f"p95={latest['p95_latency_ms']:.2f}ms "
                    f"max={latest['max_latency_ms']:.2f}ms"
                )
            next_report += max(1, report_interval)

    total_duration = time.time() - start
    if not all_chunks:
        return {
            "error": "no valid chunk was collected",
            "duration_seconds": total_duration,
            "chunks": [],
        }

    avg_fps = sum(c["effective_fps"] for c in all_chunks) / len(all_chunks)
    worst_p95 = max(c["p95_latency_ms"] for c in all_chunks)
    worst_max = max(c["max_latency_ms"] for c in all_chunks)
    result = {
        "mode": mode,
        "source": str(source),
        "duration_seconds": total_duration,
        "chunks": all_chunks,
        "chunk_count": len(all_chunks),
        "total_frames": total_frames,
        "total_read_fail": total_fail,
        "avg_effective_fps": avg_fps,
        "worst_p95_latency_ms": worst_p95,
        "worst_max_latency_ms": worst_max,
        "pass_single_response_le_1000ms": worst_max <= 1000.0,
    }

    print("=== Stability Check Summary ===")
    print(f"source={result['source']}")
    print(f"mode={result['mode']}")
    print(f"duration_seconds={result['duration_seconds']:.1f}")
    print(f"chunk_count={result['chunk_count']}")
    print(f"total_frames={result['total_frames']}")
    print(f"avg_effective_fps={result['avg_effective_fps']:.2f}")
    print(f"worst_p95_latency_ms={result['worst_p95_latency_ms']:.2f}")
    print(f"worst_max_latency_ms={result['worst_max_latency_ms']:.2f}")
    print(f"pass_single_response<=1000ms={result['pass_single_response_le_1000ms']}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage-4 performance checker")
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE),
        help="camera index (e.g. 0) or video file path",
    )
    parser.add_argument("--frames", type=int, default=300, help="frames to process (including warmup)")
    parser.add_argument("--warmup", type=int, default=20, help="warmup frames excluded from stats")
    parser.add_argument(
        "--mode",
        choices=["detect", "recognize", "recognize_emotion"],
        default="recognize",
        help="pipeline mode",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=0,
        help="if >0, run stability mode for this many seconds",
    )
    parser.add_argument(
        "--report-interval",
        type=int,
        default=15,
        help="stability mode: print periodic report every N seconds",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="optional path to write JSON summary",
    )
    args = parser.parse_args()

    source = _parse_source(str(args.source))
    if args.duration_seconds > 0:
        result = run_stability_check(
            source=source,
            mode=args.mode,
            duration_seconds=max(10, args.duration_seconds),
            report_interval=max(1, args.report_interval),
            warmup=max(0, args.warmup),
        )
        if args.output_json:
            out = Path(args.output_json)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[INFO] report saved: {out}")
        return 0 if "error" not in result else 2

    code = benchmark(source=source, frames=max(10, args.frames), warmup=max(0, args.warmup), mode=args.mode)
    if args.output_json and code == 0:
        # Re-run a minimal benchmark summary for deterministic JSON output.
        # Keep this lightweight and consistent with CLI invocation.
        # Using one short run avoids buffering all internals from benchmark().
        cv2_local = _require_cv2()
        cap = cv2_local.VideoCapture(source)
        if cap.isOpened():
            cap.release()
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "source": str(source),
                    "mode": args.mode,
                    "frames": max(10, args.frames),
                    "warmup": max(0, args.warmup),
                    "note": "Run completed; see console for full numeric summary.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[INFO] report saved: {out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
