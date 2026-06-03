# MultiCameraManagement-FacialRecognition

多摄像头人脸识别系统。当前可运行基线是 **PySide2 + OpenCV + Python 服务层**，识别主链已经切换到 **YOLOv8-face + InsightFace ArcFace + 情绪识别模型**。

当前仓库既是：

- 一个仍可直接运行的桌面版工程
- 也是后续“前后端分离化 / UI 重构 / 识别与流畅度优化”的改造基线

---

## 当前状态

当前项目已经具备：

- 登录界面、主监控界面、日志界面
- 多摄像头 / 视频源接入
- 人脸录入、删除、模型更新
- YOLOv8-face 人脸检测
- ArcFace 人脸识别
- 情绪识别模型接入
- FPS 显示、识别策略切换、日志查询、考勤记录

当前主要待解决的问题：

- UI 视觉效果和产品感不足
- 视频显示与识别推理仍存在互相影响
- 多人脸、遮挡、快速移动时识别稳定性仍不够理想
- 情绪识别和整体稳定性仍有优化空间

---

## 运行环境

- Python 3.8 - 3.10
- 建议使用 Conda 环境：`FaceReco`
- 推荐在 Windows + CUDA 环境下运行深度识别链

安装依赖：

```powershell
conda activate FaceReco
pip install -r requirements.txt
```

---

## 模型文件

### 1. 人脸检测

- 推荐模型路径：`model/yolov8n-face.pt`
- 可选兼容路径：
  - `models/yolov8n-face.pt`
  - `model/yolov10n-face.pt`
  - `models/yolov10n-face.pt`
- 环境变量覆盖：`FACE_RECO_YOLO_MODEL`

参考下载：

- YOLOv8-face：<https://github.com/derronqi/yolov8-face>
- YOLOv10-face：<https://github.com/THU-MIG/yolov10>

### 2. 人脸识别

- 识别主后端：InsightFace ArcFace
- 首次运行会下载 `buffalo_l`
- 若无法联网，可手动准备到本地 InsightFace 缓存目录

### 3. 情绪识别

- 推荐模型路径：`model/emotion_model.h5`
- 若缺失，系统会自动降级为固定 `中性`

---

## 启动当前桌面版

```powershell
conda activate FaceReco
python run.py
```

也可以使用：

```powershell
run_conda_facereco.bat
```

---

## 调优相关环境变量

### UI 帧率上限

- `FACE_RECO_UI_FPS_REALTIME`
- `FACE_RECO_UI_FPS_BALANCED`
- `FACE_RECO_UI_FPS_ACCURATE`

说明：

- `实时优先` 默认 30 FPS
- `平衡模式` 默认 18 FPS
- `高精度` 默认 15 FPS
- 设为 `0` 表示不主动限制 UI 刷新上限

示例：

```powershell
$env:FACE_RECO_UI_FPS_REALTIME="0"
python run.py
```

### YOLO / 深度识别链

- `FACE_RECO_YOLO_MODEL`
- `FACE_RECO_YOLO_CONF`
- `FACE_RECO_YOLO_IOU`
- `FACE_RECO_YOLO_IMGSZ`
- `FACE_RECO_YOLO_DEVICE`
- `FACE_RECO_DEEP_SKIP`
- `FACE_RECO_ANALYSIS_WIDTH`

### 调试

- `FACE_RECO_DEBUG=1`

开启后会输出：

- `track_id`
- `similarity`
- `match_reason`

示例：

```powershell
$env:FACE_RECO_DEBUG="1"
python run.py
```

---

## 自动化测试

运行全部测试：

```powershell
conda activate FaceReco
python -m pytest -q tests
```

基础语法检查：

```powershell
conda activate FaceReco
python -m py_compile run.py main.py
python -m compileall app services
```

---

## 当前项目结构

```text
run.py / main.py
  当前 PySide2 启动入口

app/
  repositories.py
  state.py
  services/
    app_service.py
    recognition_pipeline.py
  runtime/
    camera_stream.py
    camera_runtime.py
  ui/
    auth_windows.py
    monitor_windows.py
    log_window.py

services/
  face_detector.py
  face_recognition_service.py
  emotion_service.py
  attendance_service.py
  face_management_service.py
  camera_service.py

ui/
  Qt Designer .ui 文件

assets/
  图标与资源

model/
  YOLO / emotion / 训练产物

tests/
  自动化测试
```

---

## 当前开发重点

如果你要继续开发这个项目，建议优先关注这些文件：

- `app/runtime/camera_stream.py`
- `services/face_recognition_service.py`
- `services/face_detector.py`
- `services/emotion_service.py`
- `app/services/recognition_pipeline.py`
- `app/repositories.py`
- `app/ui/monitor_windows.py`

其中：

- `camera_stream.py` 是显示流与识别流耦合最强的热点文件
- `face_recognition_service.py` 是识别策略、阈值、后端选择的核心文件
- `monitor_windows.py` 是当前 PySide 主界面的关键控制层

---

## 并行协作开发说明

当前仓库已经进入“适合拆任务并行推进”的阶段，但**不建议多个 AI 直接并行修改主工程目录**，因为这些区域耦合较高：

- `main.py`
- `run.py`
- `app/`
- `services/`
- `ui/`
- `core/`
- `sqls.py`

推荐的并行方案是：

1. 以当前桌面版工程作为稳定基线
2. 在新的 `parallel_work/task-*` 目录下并行开发
3. 最后由专门的集成任务统一接回主工程或组装新前后端

相关文档：

- [prompt.md](prompt.md)
- [prompt_new.md](prompt_new.md)
- [parallel_task_prompts.md](parallel_task_prompts.md)

---

## 文档说明

- `prompt.md`：当前项目总览、协作约束、关键文件说明
- `prompt_new.md`：并行改造总体计划
- `parallel_task_prompts.md`：10 个可直接分发给不同 AI 的任务提示词

---

## 当前项目的定位

短期内，它仍然是一个可直接运行的桌面版识别系统。  
中期目标，是把它演进成一个更现代、更稳定、更好看的前后端分离化系统，同时保留当前工程作为迁移参考和回归基线。
