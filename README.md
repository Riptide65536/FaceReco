# MultiCameraManagement-FacialRecognition

多摄像头人脸识别系统（PySide2 + OpenCV），现已切换为深度学习识别内核（InsightFace ArcFace）。

## 环境要求

- Python 3.8 - 3.10
- 建议 Conda 环境：`FaceReco`

## 安装

```powershell
conda activate FaceReco
pip install -r requirements.txt
```

## 深度模型说明

### 1) 人脸检测+识别（InsightFace）

- 依赖：`insightface` + `onnxruntime`
- 首次运行会自动下载模型（如 `buffalo_l`）到用户缓存目录。
- 系统内识别模型文件路径：`model/model.yml`（内部为 embeddings gallery 的 npz 内容）。

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

## 测试

```powershell
python -m pytest -q
```
