from __future__ import annotations

import csv
import datetime as dt
import io
import re
import threading
import time
from pathlib import Path
from typing import Any

import cv2
from flask import Flask, Response, jsonify, request, send_from_directory, session

from app.services.app_service import AppService
from paths import BASE_DIR
from web_app.runtime import DISPLAY_MODES, WebCameraManager, normalize_source


STATIC_DIR = Path(__file__).resolve().parent / "static"
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
app.secret_key = "facereco-web-session"
service = AppService()
service.initialize_state()
camera_manager = WebCameraManager(service)
_enroll_state: dict[str, Any] = {"running": False, "message": "空闲", "captured": 0, "target": 50}
_enroll_lock = threading.RLock()
_enroll_condition = threading.Condition(_enroll_lock)
_enroll_jpeg: bytes | None = None
_train_state: dict[str, Any] = {"running": False, "message": "idle", "progress": 0, "success": None}
_train_lock = threading.RLock()


def ok(data: dict[str, Any] | None = None):
    payload = {"ok": True}
    if data:
        payload.update(data)
    return jsonify(payload)


def fail(message: str, status: int = 400):
    return jsonify({"ok": False, "message": message}), status


PUBLIC_ENDPOINTS = {"index", "static", "assets", "api_login", "api_register", "api_status"}


@app.before_request
def require_login():
    endpoint = request.endpoint or ""
    if endpoint in PUBLIC_ENDPOINTS or request.path.startswith("/assets/"):
        return None
    if session.get("account"):
        return None
    if request.path.startswith("/video/"):
        return Response(status=401)
    if request.path.startswith("/api/"):
        return fail("请先登录", 401)
    return None


def request_json() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


def camera_config(slot: int) -> dict[str, Any]:
    lines = service.config_repo.load_camera_slot(slot)
    name = lines[0] if len(lines) > 0 and lines[0] else f"监控点 {slot}"
    try:
        mode = int(lines[1]) if len(lines) > 1 else 0
    except Exception:
        mode = 0
    source = lines[2] if len(lines) > 2 and str(lines[2]).strip() else str(slot - 1)
    return {
        "slot": slot,
        "name": name,
        "displayMode": mode,
        "displayModeText": DISPLAY_MODES.get(mode, "未知模式"),
        "source": str(source),
    }


def parse_datetime(value: str | None, fallback: dt.datetime) -> dt.datetime:
    text = str(value or "").strip()
    if not text:
        return fallback
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = dt.datetime.strptime(text, fmt)
            if fmt == "%Y-%m-%d":
                return parsed.replace(hour=0, minute=0, second=0)
            return parsed
        except ValueError:
            continue
    return fallback


def clean_filter(value: str | None, empty_labels: set[str]) -> str | None:
    text = str(value or "").strip()
    if not text or text in empty_labels:
        return None
    return text


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/assets/<path:filename>")
def assets(filename: str):
    return send_from_directory(BASE_DIR / "assets", filename)


@app.get("/api/status")
def api_status():
    backend = service.pipeline.current_backend_mode()
    return ok(
        {
            "modelPending": service.is_model_pending(),
            "backendMode": backend,
            "provider": service.pipeline.current_provider_text(),
            "runtimeMode": service.state.realtime_mode,
            "showFps": service.state.show_fps_overlay,
            "users": [{"id": int(k), "name": v} for k, v in sorted(service.state.user_dic.items())],
            "customAttendance": {
                "active": bool(service.state.active_custom_attendance_label()),
                "label": service.state.active_custom_attendance_label(),
            },
            "cameras": [camera_config(i) for i in range(1, 5)],
            "runningCameras": camera_manager.statuses(),
            "authenticated": bool(session.get("account")),
            "account": session.get("account", ""),
        }
    )


@app.post("/api/login")
def api_login():
    data = request_json()
    account = str(data.get("account", "")).strip()
    password = str(data.get("password", ""))
    if not account or not password:
        return fail("请输入账号和密码")
    service.sql_repo.refresh_connection()
    if service.sql_repo.verify_login(account, password):
        session["account"] = account
        return ok({"account": account})
    return fail("账号或密码错误", 401)


@app.post("/api/register")
def api_register():
    data = request_json()
    account = str(data.get("account", "")).strip()
    password = str(data.get("password", ""))
    admin_password = str(data.get("adminPassword", ""))
    if not account or not password:
        return fail("账号和密码不能为空")
    accounts = [row[0] for row in service.sql_repo.get_all_accounts()]
    if account in accounts:
        return fail("该账号已经存在")
    if not service.sql_repo.verify_login("admin", admin_password):
        return fail("超级管理员密码错误")
    if service.sql_repo.register(account, password):
        return ok({"account": account})
    return fail("注册失败，请稍后重试", 500)


@app.get("/api/cameras/config")
def api_camera_config():
    return ok({"cameras": [camera_config(i) for i in range(1, 5)]})


@app.post("/api/cameras/config")
def api_save_camera_config():
    data = request_json()
    for item in data.get("cameras", []):
        slot = int(item.get("slot", 0))
        if slot not in (1, 2, 3, 4):
            continue
        service.config_repo.save_camera_slot(
            slot,
            str(item.get("name") or f"监控点 {slot}"),
            int(item.get("displayMode", 0)),
            str(item.get("source") or slot - 1),
        )
    return api_camera_config()


@app.post("/api/cameras/<int:slot>/start")
def api_camera_start(slot: int):
    if slot not in (1, 2, 3, 4):
        return fail("无效窗口")
    data = request_json()
    cfg = camera_config(slot)
    name = str(data.get("name") or cfg["name"])
    source = data.get("source", cfg["source"])
    display_mode = int(data.get("displayMode", cfg["displayMode"]))
    cam = camera_manager.start(slot, source, name, display_mode)
    return ok({"camera": cam.status()})


@app.post("/api/cameras/<int:slot>/stop")
def api_camera_stop(slot: int):
    camera_manager.stop(slot)
    return ok()


@app.post("/api/cameras/start-all")
def api_camera_start_all():
    for slot in range(1, 5):
        cfg = camera_config(slot)
        camera_manager.start(slot, cfg["source"], cfg["name"], cfg["displayMode"])
    return ok({"runningCameras": camera_manager.statuses()})


@app.post("/api/cameras/stop-all")
def api_camera_stop_all():
    camera_manager.stop_all()
    return ok()


@app.get("/api/cameras")
def api_cameras():
    return ok({"runningCameras": camera_manager.statuses()})


@app.get("/video/<int:slot>")
def video(slot: int):
    def generate():
        while True:
            cam = camera_manager.get(slot)
            if cam is None:
                break
            frame = cam.wait_frame(timeout=2.0)
            if frame is None:
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\nCache-Control: no-store\r\n\r\n" + frame + b"\r\n"
            time.sleep(0.001)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/runtime")
def api_runtime():
    data = request_json()
    mode = str(data.get("runtimeMode", service.state.realtime_mode)).strip()
    if mode in {"realtime", "balanced", "accurate"}:
        service.state.realtime_mode = mode
    if "showFps" in data:
        service.state.show_fps_overlay = bool(data.get("showFps"))
    return api_status()


@app.post("/api/custom-attendance/start")
def api_custom_attendance_start():
    label = str(request_json().get("label", "")).strip()
    if not label:
        return fail("请输入签到名称")
    service.state.start_custom_attendance(label)
    return api_status()


@app.post("/api/custom-attendance/stop")
def api_custom_attendance_stop():
    service.state.stop_custom_attendance()
    return api_status()


def log_filters() -> dict[str, Any]:
    now = dt.datetime.now().replace(microsecond=0)
    start = parse_datetime(request.args.get("start"), now - dt.timedelta(days=30))
    end = parse_datetime(request.args.get("end"), now)
    if start > end:
        start, end = end, start
    return {
        "name": clean_filter(request.args.get("name"), {"\u4efb\u4f55\u4eba\u5458", "\u6d5c\u8b83\u7dbd\u6d5c\u54c4"}),
        "location": clean_filter(request.args.get("location"), {"\u4efb\u4f55\u5730\u70b9", "\u6d5c\u8b83\u7dbd\u9366\u6276"}),
        "start_time": start,
        "end_time": end,
        "attendance_type": clean_filter(request.args.get("attendanceType"), {"\u4efb\u4f55\u7c7b\u578b", "\u6d5c\u8b83\u7dbd\u7c7b"}),
        "status": clean_filter(request.args.get("status"), {"\u4efb\u4f55\u72b6\u6001", "\u6d5c\u8b83\u7dbd\u9418"}),
    }


@app.get("/api/logs")
def api_logs():
    rows = service.sql_repo.query_logs_with_emotion(**log_filters())
    return ok(
        {
            "rows": [
                {
                    "name": row[0] if len(row) > 0 else "",
                    "location": row[1] if len(row) > 1 else "",
                    "time": str(row[2] if len(row) > 2 else ""),
                    "emotion": row[3] if len(row) > 3 else "",
                    "attendanceType": row[4] if len(row) > 4 else "",
                    "status": row[5] if len(row) > 5 else "",
                }
                for row in rows
            ]
        }
    )


@app.get("/api/logs/filters")
def api_log_filters():
    names = [str(row[0]) for row in service.sql_repo.get_all_names() if row and row[0]]
    places = [str(row[0]) for row in service.sql_repo.get_all_places() if row and row[0]]
    types = [str(row[0]) for row in service.sql_repo.get_all_attendance_types() if row and row[0]]
    return ok({"names": names, "places": places, "attendanceTypes": types})


@app.post("/api/logs/clear")
def api_logs_clear():
    if service.sql_repo.reset_logs():
        return ok()
    return fail("日志数据库清空失败", 500)


@app.get("/api/logs/absence")
def api_absence():
    day_text = request.args.get("day") or dt.datetime.now().strftime("%Y-%m-%d")
    day = dt.datetime.strptime(day_text, "%Y-%m-%d").date()
    names = sorted(set(service.state.user_dic.values()))
    return ok({"day": day_text, "rows": service.sql_repo.get_absence_list(names, day=day)})


@app.get("/api/logs/summary")
def api_summary():
    rows = service.sql_repo.query_logs_with_emotion(**log_filters())
    summary: dict[str, dict[str, int]] = {}
    for row in rows:
        name = str(row[0] if row and row[0] else "未知人员")
        status = str(row[5] if len(row) > 5 and row[5] else "未分类")
        summary.setdefault(name, {})
        summary[name][status] = summary[name].get(status, 0) + 1
    return ok({"total": len(rows), "summary": summary})


@app.get("/api/logs/export")
def api_export_logs():
    rows = service.sql_repo.query_logs_with_emotion(**log_filters())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["姓名", "地点", "时间", "情绪", "考勤类型", "状态"])
    for row in rows:
        values = list(row)
        values.extend([""] * (6 - len(values)))
        writer.writerow(values[:6])
    csv_bytes = output.getvalue().encode("utf-8-sig")
    filename = f"attendance_report_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def sanitize_username(raw_name: str) -> tuple[str, str]:
    name = str(raw_name or "").strip()
    if not name:
        return "", "你还没有输入姓名"
    if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9_]+", name) is None:
        return "", "姓名仅允许中文、英文、数字、下划线"
    return name, ""


@app.post("/api/enroll/capture")
def api_enroll_capture():
    data = request_json()
    username, reason = sanitize_username(str(data.get("username", "")))
    if not username:
        return fail(reason)
    target = max(1, min(100, int(data.get("target", 50))))
    source = normalize_source(data.get("source", 0))
    threading.Thread(target=_capture_worker_web, args=(username, target, source), daemon=True).start()
    return ok({"message": "采集已开始"})


def _capture_worker_web(username: str, target: int, source: Any) -> None:
    global _enroll_jpeg
    with _enroll_lock:
        if _enroll_state.get("running"):
            return
        _enroll_jpeg = None
        _enroll_state.update({"running": True, "message": "opening camera", "captured": 0, "target": target})
        _enroll_condition.notify_all()

    user_dir = service.data_repo.recreate_user_dir(username)
    service.ensure_user_registered(username)
    restore_snapshots = camera_manager.stop_matching_source(source)
    cap = cv2.VideoCapture(source)
    captured = 0
    try:
        if not cap.isOpened():
            with _enroll_lock:
                _enroll_state.update({"running": False, "message": "camera open failed"})
                _enroll_condition.notify_all()
            return

        detector = service.pipeline.face_service if service.pipeline.ensure_face_service_ready() else None
        start = time.monotonic()
        while captured < target and time.monotonic() - start < 30:
            ok_frame, frame = cap.read()
            if not ok_frame:
                time.sleep(0.02)
                continue
            frame = cv2.resize(frame, (640, 360))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = []
            if detector is not None:
                try:
                    faces = detector.detect_faces(frame)
                except Exception:
                    faces = []
            if not faces and service.pipeline._fallback_detector is not None:
                try:
                    faces = service.pipeline._fallback_detector.detectMultiScale(gray, 1.3, 5)
                except Exception:
                    faces = []

            for x, y, w, h in faces:
                x, y, w, h = int(x), int(y), int(w), int(h)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (30, 128, 255), 2)
                if captured >= target:
                    break
                crop = gray[max(0, y) : max(0, y + h), max(0, x) : max(0, x + w)]
                if crop.size == 0:
                    continue
                captured += 1
                service.data_repo.write_face_image(user_dir / f"{captured}.jpg", crop)
                with _enroll_lock:
                    _enroll_state.update({"captured": captured, "message": "capturing samples"})

            ok_jpeg, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
            if ok_jpeg:
                with _enroll_lock:
                    _enroll_jpeg = jpeg.tobytes()
                    _enroll_condition.notify_all()
            time.sleep(0.03)

        if captured > 0:
            service.mark_model_pending()
            service.persist_training_state()
        with _enroll_lock:
            message = "capture finished, please update model" if captured > 0 else "no face captured"
            _enroll_state.update({"running": False, "captured": captured, "message": message})
            _enroll_condition.notify_all()
    finally:
        cap.release()
        camera_manager.restore_snapshots(restore_snapshots)


def _capture_worker(username: str, target: int, source: Any) -> None:
    with _enroll_lock:
        if _enroll_state.get("running"):
            return
        _enroll_state.update({"running": True, "message": "正在打开摄像头", "captured": 0, "target": target})
    user_dir = service.data_repo.recreate_user_dir(username)
    service.ensure_user_registered(username)
    cap = cv2.VideoCapture(source)
    captured = 0
    try:
        if not cap.isOpened():
            with _enroll_lock:
                _enroll_state.update({"running": False, "message": "摄像头无法打开"})
            return
        detector = None
        if service.pipeline.ensure_face_service_ready():
            detector = service.pipeline.face_service
        start = time.monotonic()
        while captured < target and time.monotonic() - start < 30:
            ok_frame, frame = cap.read()
            if not ok_frame:
                continue
            frame = cv2.resize(frame, (640, 360))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = []
            if detector is not None:
                try:
                    faces = detector.detect_faces(frame)
                except Exception:
                    faces = []
            if not faces and service.pipeline._fallback_detector is not None:
                try:
                    faces = service.pipeline._fallback_detector.detectMultiScale(gray, 1.3, 5)
                except Exception:
                    faces = []
            for x, y, w, h in faces:
                if captured >= target:
                    break
                crop = gray[int(y) : int(y + h), int(x) : int(x + w)]
                if crop.size == 0:
                    continue
                captured += 1
                service.data_repo.write_face_image(user_dir / f"{captured}.jpg", crop)
                with _enroll_lock:
                    _enroll_state.update({"captured": captured, "message": "正在采集样本"})
            time.sleep(0.03)
        service.mark_model_pending()
        service.persist_training_state()
        with _enroll_lock:
            _enroll_state.update({"running": False, "captured": captured, "message": "采集完成，请更新模型"})
    finally:
        cap.release()


@app.get("/api/enroll/status")
def api_enroll_status():
    with _enroll_lock:
        return ok({"enroll": dict(_enroll_state)})


@app.get("/video/enroll")
def enroll_video():
    def generate():
        while True:
            with _enroll_condition:
                if _enroll_jpeg is None:
                    _enroll_condition.wait(timeout=2.0)
                frame = _enroll_jpeg
                running = bool(_enroll_state.get("running"))
            if frame is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\nCache-Control: no-store\r\n\r\n" + frame + b"\r\n"
            if not running:
                break
            time.sleep(0.001)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/model/train")
def api_model_train():
    with _train_lock:
        if _train_state.get("running"):
            return ok({"training": dict(_train_state)})
        _train_state.update({"running": True, "message": "preparing samples", "progress": 0, "success": None})
    threading.Thread(target=_train_model_worker_web, daemon=True).start()
    return ok({"training": dict(_train_state)})


def _api_model_train_legacy_unused():
    samples, labels = service.pipeline.rebuild_training_data(service.data_repo)
    if len(samples) != len(labels):
        return fail("训练数据异常")
    if service.train_with_samples(samples, labels):
        return api_status()
    return fail(service.pipeline.last_train_error_text() or "模型更新失败", 500)


@app.get("/api/model/train/status")
def api_model_train_status():
    with _train_lock:
        return ok({"training": dict(_train_state)})


def _train_model_worker_web() -> None:
    snapshots = camera_manager.statuses()
    try:
        camera_manager.stop_all()
        with _train_lock:
            _train_state.update({"message": "loading samples", "progress": 1})
        samples, labels = service.pipeline.rebuild_training_data(service.data_repo)
        if len(samples) != len(labels):
            raise RuntimeError("training data error")
        with _train_lock:
            _train_state.update({"message": "training model", "progress": 2})
        if not service.train_with_samples(samples, labels):
            raise RuntimeError(service.pipeline.last_train_error_text() or "model update failed")
        service.state.update_user_stats()
        with _train_lock:
            _train_state.update({"running": False, "message": "model updated", "progress": 4, "success": True})
    except Exception as exc:
        with _train_lock:
            _train_state.update({"running": False, "message": str(exc), "progress": 4, "success": False})
    finally:
        camera_manager.restore_snapshots(snapshots)


@app.post("/api/model/reset")
def api_model_reset():
    camera_manager.stop_all()
    service.reset_face_data()
    return api_status()


@app.post("/api/users/delete")
def api_user_delete():
    username = str(request_json().get("username", "")).strip()
    if not username:
        return fail("请选择要删除的用户")
    if service.delete_user_only(username):
        return api_status()
    return fail("删除失败", 500)


def main() -> None:
    app.run(host="127.0.0.1", port=5000, threaded=True)


if __name__ == "__main__":
    main()
