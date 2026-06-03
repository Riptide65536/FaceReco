# Task-00 Contracts

本目录是并行改造阶段的“统一语言层”。它不包含业务实现，只定义当前仓库的真实基线、接口边界、事件结构、迁移蓝图和集成约束。

## 目录说明

- `architecture_baseline.md`：当前真实启动链、识别链、训练链、日志链，以及可复用/建议重写模块。
- `migration_map.md`：从现有 PySide2 工程迁移到前后端分离形态的任务映射与阶段计划。
- `api_contract.yaml`：前后端 REST / WebSocket 契约草案。
- `event_schema.md`：视频帧、检测、识别、情绪、告警、系统状态的数据结构。
- `change_request_log.md`：公共边界变更请求登记。
- `test_report.md`：本任务自测与核对结果。

## 使用顺序

建议所有并行任务按下面顺序阅读：

1. `architecture_baseline.md`
2. `event_schema.md`
3. `api_contract.yaml`
4. `migration_map.md`
5. `change_request_log.md`

## 并行阶段硬规则

- 当前可运行基线是 PySide2 桌面程序。
- 旧工程目录默认只读参考。
- 非 Task-08 不得修改主工程保护区。
- 新实现优先放在各自 `parallel_work/task-*` 目录。
- 任何公共边界变化先登记到 `change_request_log.md`。

## 本目录冻结的关键结论

- 真实启动链是 `run.py -> main.py -> auth window -> monitor window -> services/runtime/services`。
- 真实识别主链是 `YOLOv8-face + InsightFace ArcFace + emotion_model.h5`，并有 `LBPH / lite` 回退。
- 当前最大热点是 `app/runtime/camera_stream.py`，它不适合直接多人并行修改。
- 并行阶段统一数据结构命名为：
  - `FramePacket`
  - `DetectionResult`
  - `RecognitionResult`
  - `EmotionResult`
  - `AlertResult`
  - `VisionObservation`

## 给 Task-01 ~ Task-09 的使用建议

- Task-01：以后端 adapter 为主，不要把 Qt 窗口逻辑搬进新服务。
- Task-02：仅依赖本目录契约，不依赖旧 UI 类名。
- Task-03：检测/识别输出统一对齐 `event_schema.md`。
- Task-04：情绪输出统一对齐 `event_schema.md`。
- Task-05：运行时拆分以 `FramePacket` 和 `VisionObservation` 为边界。
- Task-06：任何新功能对外暴露时优先复用现有 API 与事件结构。
- Task-07：异常、降级、离线统一通过 `SystemStatus` / `AlertResult` 表达。
- Task-08：集成前先核对本目录，再决定如何回接主工程。
- Task-09：测试目标不是“像不像某个实现”，而是“是否遵守契约并且不破坏旧基线”。
