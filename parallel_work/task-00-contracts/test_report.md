# Task-00 自测报告

## 1. 结论

本任务要求的文档产物已经生成完成，并完成了命名一致性与路径一致性核对。

结果：

- 必交文件检查：通过
- 冻结术语一致性检查：通过
- 仓库真实路径存在性检查：通过
- 越界修改检查：通过

## 2. 已生成文件

- `architecture_baseline.md`
- `migration_map.md`
- `api_contract.yaml`
- `event_schema.md`
- `change_request_log.md`
- `README.md`
- `test_report.md`

## 3. 我核对过的源文件

### 3.1 协作文档

- `prompt.md`
- `prompt_new.md`

### 3.2 启动与装配

- `run.py`
- `main.py`
- `paths.py`
- `app/state.py`

### 3.3 服务与运行时

- `app/services/app_service.py`
- `app/services/recognition_pipeline.py`
- `app/runtime/camera_stream.py`
- `app/repositories.py`
- `services/face_detector.py`
- `services/face_recognition_service.py`
- `services/emotion_service.py`
- `services/attendance_service.py`

### 3.4 UI 与日志

- `app/ui/auth_windows.py`
- `app/ui/monitor_windows.py`
- `app/ui/log_window.py`

### 3.5 数据库与表结构

- `core/sql_helper.py`
- `init_db.sql`

### 3.6 测试文件

- `tests/test_app_service.py`
- `tests/test_face_recognition_contract.py`
- `tests/test_emotion_service_contract.py`
- `tests/test_real_time_balancing_contract.py`
- `tests/test_recognition_pipeline_deep_contract.py`
- `tests/test_attendance.py`

## 4. 自测项与结果

### 4.1 必交文件是否齐全

检查结果：通过

已确认存在：

- `architecture_baseline.md`
- `migration_map.md`
- `api_contract.yaml`
- `event_schema.md`
- `change_request_log.md`
- `README.md`

### 4.2 接口命名是否前后一致

检查结果：通过

已统一并在 Markdown / YAML 中交叉出现的冻结名称：

- `FramePacket`
- `DetectionResult`
- `RecognitionResult`
- `EmotionResult`
- `AlertResult`
- `VisionObservation`
- `EventEnvelope`
- `SystemStatus`

### 4.3 文档中的关键路径是否与仓库一致

检查结果：通过

以下路径已逐个存在性核对，结果均为 `True`：

- `run.py`
- `main.py`
- `app/services/app_service.py`
- `app/services/recognition_pipeline.py`
- `app/runtime/camera_stream.py`
- `app/repositories.py`
- `services/face_detector.py`
- `services/face_recognition_service.py`
- `services/emotion_service.py`
- `services/attendance_service.py`
- `app/ui/monitor_windows.py`
- `app/ui/log_window.py`
- `app/ui/auth_windows.py`
- `core/sql_helper.py`
- `config/configwin1.txt`
- `config/configwin2.txt`
- `config/configwin3.txt`
- `config/configwin4.txt`
- `model`
- `data`
- `tests`
- `prompt.md`
- `prompt_new.md`

### 4.4 是否遵守任务边界

检查结果：通过

本次新增文件全部位于：

- `parallel_work/task-00-contracts/`

未修改主工程目录中的业务代码。

## 5. 未执行项与说明

- 未运行 `pytest`：本任务不修改主工程实现代码，目标是契约与文档冻结，不是代码逻辑回归。
- 未做 YAML 解析器级语法校验：当前环境未提供现成 YAML 解析工具；已通过人工校对和命名一致性检查降低风险。
- 未启动桌面程序：本任务只读分析主工程，不改变其运行行为。

## 6. 对 Task-08 / Task-09 的建议

- Task-08 集成前先以本文件为检查单，确认字段名没有漂移。
- Task-09 可以把第 4 节直接转成 smoke checklist 的一部分。
