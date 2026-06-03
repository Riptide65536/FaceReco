# Task-00 变更请求日志

## 1. 用途

本文件记录会影响并行任务公共边界的变更请求。

并行阶段规则：

- 默认契约以本目录文件为准。
- 影响公共字段、接口路径、事件类型、主工程接入方式的改动，必须先登记。
- 只有 Task-08 可以在最终集成阶段真正修改主工程保护区。

## 2. 状态定义

- `proposed`：提出，尚未集成
- `accepted_for_integration`：已接受，等待 Task-08 集成
- `rejected`：拒绝
- `merged`：已由 Task-08 接入主工程

## 3. 记录格式

| ID | 日期 | 提出方 | 状态 | 影响范围 | 请求内容 | 集成建议 |
| --- | --- | --- | --- | --- | --- | --- |

## 4. 当前已登记请求

| ID | 日期 | 提出方 | 状态 | 影响范围 | 请求内容 | 集成建议 |
| --- | --- | --- | --- | --- | --- | --- |
| `CR-001` | `2026-06-03` | `Task-00` | `proposed` | `model/model.yml`, `services/face_recognition_service.py`, `app/repositories.py` | 当前深度/Lite 模式实际读写 `npz` embedding gallery，但默认文件名仍为 `model.yml`。这会让后端 API、测试和运维误判模型格式。 | 并行阶段保持兼容读取；Task-08 集成时可新增更明确的 canonical 文件名或 `model_format` 元数据，但不得破坏旧路径读取。 |
| `CR-002` | `2026-06-03` | `Task-00` | `proposed` | `app/runtime/camera_stream.py`, `app/services/*`, `core/sql_helper.py` | 当前运行时层直接决定何时把识别结果写库，导致采集/推理/持久化无法独立演进。 | Task-08 集成时应让新 backend runtime 先产出 `VisionObservation`，再由后端 service 决定持久化与告警。旧 Qt 路径可保留兼容模式。 |
| `CR-003` | `2026-06-03` | `Task-00` | `proposed` | `config/configwin*.txt`, 新后端 camera 配置` | 当前旧工程以 1~4 槽位文件保存摄像头配置，新系统需要区分 `camera_id` 与 `slot_id`。 | 新后端先采用 `camera_id` 为主键；Task-08 如需兼容旧配置，做导入映射，不继续把槽位当摄像头主键。 |

## 5. 对 Task-01 ~ Task-09 的使用建议

- Task-01：若 API 路径想调整，先看本文件是否已有相关请求。
- Task-02：页面字段名不要自行改动；若确需改，先登记请求。
- Task-03：算法输出扩展允许新增字段，不允许重命名冻结字段。
- Task-04：情绪标签集合如需扩展，也应登记说明是否影响前端枚举。
- Task-05：若需要改变 `frame_id`、`camera_id`、`track_id` 语义，必须登记。
- Task-06：新增告警类型前，先沿用本文件已冻结的 `AlertResult`。
- Task-07：降级状态如果想新增事件类型，先登记。
- Task-08：集成前先扫一遍本文件，按状态执行。
- Task-09：测试时可将本文件作为“契约漂移清单”。
