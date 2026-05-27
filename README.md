# MultiCameraManagement-FacialRecognition

多摄像头人脸识别系统（PySide2 + OpenCV），现已切换为深度学习识别内核（YOLOv8-face 检测 + InsightFace ArcFace 识别）。

## 环境要求

- Python 3.8 - 3.10
- 建议 Conda 环境：`FaceReco`

## 安装

```powershell
conda activate FaceReco
pip install -r requirements.txt
```

## 深度模型说明

### 1) 人脸检测（YOLOv8-face）+ 人脸识别（InsightFace ArcFace）

- 依赖：`ultralytics` + `insightface` + `onnxruntime`
- YOLOv8-face 模型下载地址：`https://github.com/derronqi/yolov8-face`
- YOLOv10-face 参考地址：`https://github.com/THU-MIG/yolov10`
- 默认检测模型查找顺序：
  - `model/yolov8n-face.pt`
  - `models/yolov8n-face.pt`
  - `model/yolov10n-face.pt`
  - `models/yolov10n-face.pt`
- 如需自定义路径，可设置环境变量：`FACE_RECO_YOLO_MODEL`
- InsightFace 的 `buffalo_l` 首次运行会自动下载到用户缓存目录；若无法联网，可手动放到：`~/.insightface/models/buffalo_l`
- 系统内识别 gallery 文件路径：`model/model.yml`（内部为 embeddings gallery 的 npz 内容）

### 2) 情绪识别（CNN .h5）

- 文件路径：`model/emotion_model.h5`
- 若文件不存在，系统自动回退为 `中性`，不影响主识别流程。

## 运行

```powershell
python run.py
```

或：

```powershell
run_conda_facereco.bat
```

## 运行调优与调试

### 1) UI 模式与 FPS 上限

- 主界面支持三种识别策略：`实时优先`、`平衡模式`、`高精度`
- 默认 UI 输出上限：
  - `实时优先`：30 FPS
  - `平衡模式`：18 FPS
  - `高精度`：15 FPS
- 可通过环境变量覆盖：
  - `FACE_RECO_UI_FPS_REALTIME`
  - `FACE_RECO_UI_FPS_BALANCED`
  - `FACE_RECO_UI_FPS_ACCURATE`
- 当某个 FPS 环境变量设为 `0` 时，表示该模式下不主动限制 UI 刷新上限

示例：

```powershell
$env:FACE_RECO_UI_FPS_REALTIME="0"
python run.py
```

### 2) FPS 叠加层

- 监控主界面提供“显示 FPS / 隐藏 FPS”按钮
- 开启后，会在每个视频窗口左下角显示实时 FPS 数值

### 3) YOLO 与识别链路调优

- `FACE_RECO_YOLO_MODEL`：自定义 YOLOv8-face 权重路径
- `FACE_RECO_YOLO_CONF`：YOLO 检测置信度阈值，默认 `0.25`
- `FACE_RECO_YOLO_IOU`：YOLO NMS IoU 阈值，默认 `0.45`
- `FACE_RECO_YOLO_IMGSZ`：YOLO 推理尺寸，默认 `640`
- `FACE_RECO_YOLO_DEVICE`：指定推理设备，例如 `cpu`、`0`
- `FACE_RECO_DEEP_SKIP`：隔多少帧触发一次识别分析
- `FACE_RECO_ANALYSIS_WIDTH`：识别分析时使用的缩放宽度

### 4) 稳定性与调试

- `FACE_RECO_DEBUG=1` 时，会输出每个检测框的 `track_id`、`similarity`、`match_reason`
- 调试模式下，画面叠加层也会显示轨迹和匹配状态，便于判断闪烁、误匹配、重复框等问题

示例：

```powershell
$env:FACE_RECO_DEBUG="1"
python run.py
```

## 测试

```powershell
python -m pytest -q
```
