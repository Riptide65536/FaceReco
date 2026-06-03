# Task-00 架构基线

## 1. 目标与范围

本文件只描述当前仓库已经存在、已经可运行的真实结构，并据此冻结并行改造阶段的统一术语。

- 这是一个 **PySide2 桌面程序**，不是已经完成前后端分离的系统。
- 当前稳定基线仍然是旧工程目录。
- 本任务不改业务代码，只给 Task-01 ~ Task-09 提供统一边界。

## 2. 当前真实启动链路

### 2.1 启动入口

真实启动顺序如下：

```text
run.py
  -> main.py
    -> QApplication
    -> app/ui/auth_windows.py::LogInWindow
    -> app/services/app_service.py::AppService
    -> app/ui/monitor_windows.py::configure(...)
    -> 登录成功后创建 app/ui/monitor_windows.py::MWindow
```

关键事实：

- `run.py` 只做 Python 版本与依赖检查，然后 `import main`。
- `main.py` 在模块顶层直接创建 `QApplication`、`AppService`、`LogInWindow`。
- 登录成功后才创建 `MWindow`。
- `MWindow.__init__()` 内部会调用 `AppService.initialize_state()` 初始化配置、数据目录、用户字典和训练样本缓存。

### 2.2 摄像头与识别主链

主监控窗口启动单路视频的真实链路如下：

```text
MWindow.start_slot(...)
  -> app/runtime/camera_stream.py::Camera(...)
  -> Camera.display() / displaySimpleBrand() / displayJustdisplayBrand()
  -> services/face_recognition_service.py::FaceRecognitionService
  -> services/emotion_service.py::EmotionRecognitionService
  -> app/repositories.py::SqlRepository
  -> core/sql_helper.py::SqlF.saveNameTimePic(...)
```

关键事实：

- `MWindow.start_slot()` 负责视频源解析、窗口占用检查、系统摄像头互斥锁、线程启动。
- `Camera.display()` 内部同时承担：
  - 帧采集与显示
  - 检测/识别调度
  - 跟踪与结果平滑
  - 情绪缓存与异步推理
  - 识别结果聚合后写库
- 当前 `camera_stream.py` 是最强耦合热点文件。

### 2.3 模型训练链路

真实训练链路如下：

```text
MWindow -> LuruWindow.trainModel()
  -> app/services/app_service.py::train_with_samples()
  -> app/services/recognition_pipeline.py::train_and_save()
  -> services/face_recognition_service.py::train()
  -> model/model.yml
```

关键事实：

- 训练样本来自 `data/` 目录下的用户图片。
- `RecognitionPipeline.rebuild_training_data()` 负责重建训练集。
- 深度/Lite 模式会直接把整张灰度样本送去提 embedding，不再重复做人脸检测。
- `FaceRecognitionService` 在 `deep/lite` 模式下实际写入的是 `np.savez_compressed(...)` 压缩数据，但默认路径名称仍叫 `model.yml`。

### 2.4 日志与考勤链路

真实日志查询链路如下：

```text
MWindow.log()
  -> app/ui/log_window.py::LogWindow
  -> app/repositories.py::SqlRepository
  -> core/sql_helper.py::query_logs_with_emotion(...)
```

真实入库链路如下：

```text
Camera._save_detected_recognition_event(...)
  -> SqlRepository.save_recognition_event(...)
  -> SqlF.saveNameTimePic(...)
  -> recognition_logs + attendance_records
```

关键事实：

- 当前日志与考勤不是两套完全独立系统。
- `saveNameTimePic(...)` 会同时写 `recognition_logs` 和 `attendance_records`。
- `AttendanceService` 会根据当天已有记录自动推导：
  - `上班打卡`
  - `下班打卡`
  - `重复识别`
  - `未识别`
  - 状态如 `正常 / 迟到 / 早退 / 已记录 / 异常`

## 3. 当前真实算法与回退链

### 3.1 人脸检测

主检测能力：

- 首选：`services/face_detector.py::YOLOFaceDetector`
- 回退：`services/face_detector.py::InsightFaceDetector`
- 更旧回退：Haar 级联，主要留在 `RecognitionPipeline` 和 `Camera` 的兼容路径中

### 3.2 人脸识别

真实后端模式由 `FaceRecognitionService.backend_mode()` 暴露：

- `deep`：InsightFace ArcFace embedding + gallery 匹配
- `lbph`：OpenCV LBPH 降级
- `lite`：轻量像素特征应急降级

### 3.3 情绪识别

- 文件：`services/emotion_service.py`
- 模型：`model/emotion_model.h5`
- 缺失或失败时回退：固定返回 `中性`, `0.0`

### 3.4 实时策略

当前运行时已经存在三种模式，保留为并行改造阶段的公共枚举：

- `realtime`
- `balanced`
- `accurate`

当前 FPS 显示开关同样已存在：

- `AppState.show_fps_overlay`

## 4. 当前目录与职责

| 路径 | 当前职责 | 结论 |
| --- | --- | --- |
| `run.py` | 启动前依赖检查 | 旧入口，保留 |
| `main.py` | Qt 应用装配 | 旧入口，保留 |
| `app/services/app_service.py` | 上层服务聚合、状态初始化、训练与删除入口 | 可复用为后端适配参考 |
| `app/services/recognition_pipeline.py` | 识别/训练编排，弱 UI 依赖 | 可复用为领域服务参考 |
| `app/runtime/camera_stream.py` | 采集、显示、推理、跟踪、情绪、写库混合实现 | 建议拆分重写 |
| `app/repositories.py` | 配置、数据目录、数据库访问封装 | 可复用为 legacy adapter |
| `services/face_detector.py` | 检测器抽象与 YOLO/InsightFace 适配 | 高价值复用 |
| `services/face_recognition_service.py` | 深度/LBPH/Lite 多后端识别核心 | 高价值复用 |
| `services/emotion_service.py` | 情绪识别与平滑 | 高价值复用 |
| `services/attendance_service.py` | 考勤类型与状态判定 | 高价值复用 |
| `app/ui/monitor_windows.py` | 监控主窗体、摄像头配置、训练入口 | 仅作交互参考，前端建议重写 |
| `app/ui/log_window.py` | 日志/考勤查询界面 | 仅作交互参考，前端建议重写 |
| `app/ui/auth_windows.py` | 登录/注册界面 | 仅作交互参考，前端建议重写 |
| `core/sql_helper.py` | 底层表结构与日志/考勤持久化 | 可复用为后端 repository 基础 |

## 5. 可复用模块与建议重写模块

### 5.1 建议直接复用或包装复用

- `services/face_detector.py`
- `services/face_recognition_service.py`
- `services/emotion_service.py`
- `services/attendance_service.py`
- `app/services/app_service.py`
- `app/services/recognition_pipeline.py`
- `app/repositories.py`
- `core/sql_helper.py`

复用方式建议：

- Task-01 以后端适配层包装这些服务，不要把 PySide UI 依赖带进新后端。
- Task-03/04 优先围绕已有服务做增强版实现或兼容适配，不要发明第二套字段名。
- Task-08 再决定是否把增强实现接回主工程。

### 5.2 建议重写或拆分

- `app/runtime/camera_stream.py`
- `app/ui/monitor_windows.py`
- `app/ui/log_window.py`
- `app/ui/auth_windows.py`
- `main.py`
- `run.py`

重写原因：

- `camera_stream.py` 同时负责显示、推理、缓存、跟踪、考勤入库，边界过厚。
- 现有 UI 逻辑默认绑定 Qt 控件，不适合作为 Web 前端直接复用。
- 启动链路是桌面应用装配，不适合作为新系统唯一入口。

## 6. 前后端接口边界

### 6.1 后端必须负责

- 摄像头源管理
- 实时运行时与降级策略
- 人脸检测/识别/情绪推理
- 跟踪与结果稳定
- 模型训练与模型待更新状态
- 日志、考勤、用户样本与配置持久化
- 告警生成
- 对外 REST / WebSocket 契约

### 6.2 前端必须负责

- 登录表单、监控大屏、日志页、考勤页、样本管理页
- 摄像头布局、筛选、展示节奏
- 对后端事件的可视化
- 用户触发的配置修改、启动/停止、训练、删除、导出

### 6.3 前端不应直接负责

- 直接读写 `config/*.txt`
- 直接读写 `data/` 或 `model/`
- 直接操作数据库
- 直接调用 `services/*.py`

## 7. 并行阶段权限边界

### 7.1 主工程保护区

以下路径在并行阶段默认视为只读参考：

- `run.py`
- `main.py`
- `app/`
- `services/`
- `core/`
- `ui/`
- `sqls.py`
- `README.md`

### 7.2 谁能改主工程

- `Task-00`：不能改主工程，只能冻结契约。
- `Task-01 ~ Task-07`：不能改主工程，只能在各自 `parallel_work/task-*` 下开发。
- `Task-09`：不能改主工程，只做测试与验证材料。
- `Task-08`：**唯一允许在集成阶段接触主工程目录的任务**。

## 8. 需要特别提醒的兼容风险

### 8.1 模型文件名与内容格式不一致

- 路径默认名：`model/model.yml`
- 深度/Lite 实际内容：`npz` 压缩 embedding gallery
- LBPH 实际内容：OpenCV recognizer 文件

结论：

- 并行阶段不要假设 `model.yml` 一定是 YAML。
- 新后端必须显式暴露 `backend_mode` 和 `model_pending`。

### 8.2 当前入库发生在运行时层

`Camera.display()` 聚合到一定次数后直接写库，这意味着：

- 当前“识别成功”和“记录入库”不是严格分层的两步。
- 新后端需要把“观察结果”与“持久化决策”拆开。

### 8.3 当前摄像头身份是“槽位 + 源地址”混合模型

当前代码同时存在：

- 固定槽位：1~4
- 视频源：`0`、本地视频文件、流地址

新契约必须区分：

- `camera_id`：逻辑摄像头 ID
- `slot_id`：前端布局槽位，可选

## 9. Task-01 ~ Task-09 的使用建议

- Task-01：把 `AppService + RecognitionPipeline + repositories + sql_helper` 视为后端 adapter 参考，不要复刻 Qt 调用链。
- Task-02：以前端页面重写为主，不要依赖 PySide 控件命名；只依赖 `api_contract.yaml` 与 `event_schema.md`。
- Task-03：输出 `DetectionResult` / `RecognitionResult` 时必须兼容本任务命名。
- Task-04：输出 `EmotionResult`，并保留 `emotion/confidence/quality/reason` 四元组。
- Task-05：负责把现有 `Camera.display()` 拆成采集、推理、渲染可解耦的运行时，不要直接改旧 `camera_stream.py`。
- Task-06：新功能产生的告警必须走 `AlertResult`，不要自定义另一套字段。
- Task-07：降级、离线、模型待更新等状态统一并入 `system.status` 或 `alert.raised` 事件。
- Task-08：集成时严格以本目录契约为准，凡是要动主工程的地方先看 `change_request_log.md`。
- Task-09：测试时同时验证 legacy 基线未破坏，以及新模块是否遵守本目录契约命名。
