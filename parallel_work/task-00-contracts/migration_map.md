# Task-00 迁移蓝图

## 1. 迁移原则

1. 并行阶段不直接改主工程。
2. 新系统先在 `parallel_work/task-*` 下完成各自最小可运行切片。
3. 统一接口先冻结，再并行开发，再由 Task-08 集成。
4. 新系统默认采用“前端展示 / 后端推理与持久化”分层。

## 2. 当前结构到目标结构的映射

| 当前路径 | 当前职责 | 目标归宿 | 建议动作 | 主要任务 |
| --- | --- | --- | --- | --- |
| `run.py` | 旧入口 | legacy 启动入口 | 保留，不并行修改 | Task-08 |
| `main.py` | Qt 装配 | legacy 启动入口 | 保留，不并行修改 | Task-08 |
| `app/ui/auth_windows.py` | 登录/注册窗体 | Web 登录页 + Auth API | 重写 UI，保留登录语义 | Task-01, Task-02 |
| `app/ui/monitor_windows.py` | 主监控窗体 | Web 监控页 + Camera API | 重写 UI；保留摄像头配置语义 | Task-01, Task-02 |
| `app/ui/log_window.py` | 日志与考勤查询 | Web 日志/报表页 | 重写 UI；保留筛选条件与字段 | Task-01, Task-02 |
| `app/runtime/camera_stream.py` | 采集+显示+推理+写库 | Backend runtime + event bus | 按职责拆分重写 | Task-03, Task-04, Task-05, Task-07 |
| `app/services/app_service.py` | 应用服务聚合 | Backend service facade | 适配复用 | Task-01 |
| `app/services/recognition_pipeline.py` | 训练/识别编排 | Domain orchestration | 适配复用 | Task-01, Task-03, Task-04 |
| `app/repositories.py` | 配置/样本/DB 仓储 | Backend repositories | 适配复用 | Task-01 |
| `services/face_detector.py` | 检测器抽象 | Face engine | 直接复用或增强 | Task-03 |
| `services/face_recognition_service.py` | 识别引擎 | Face engine | 直接复用或增强 | Task-03 |
| `services/emotion_service.py` | 情绪识别 | Emotion engine | 直接复用或增强 | Task-04 |
| `services/attendance_service.py` | 考勤判定 | Attendance domain | 直接复用 | Task-01, Task-06 |
| `core/sql_helper.py` | 表结构与日志写库 | Backend persistence | 适配复用 | Task-01 |

## 3. 推荐的目标分层

```text
Frontend (Task-02)
  -> REST API / WebSocket

Backend API (Task-01)
  -> camera application service
  -> recognition application service
  -> attendance/log service
  -> config/sample/model service

Runtime / Engines
  -> stream runtime (Task-05)
  -> face engine (Task-03)
  -> emotion engine (Task-04)
  -> safety/observability (Task-07)

Persistence
  -> repositories / sql_helper adapter

Integration
  -> Task-08
```

## 4. 推荐拆分方式

### 4.1 将 `camera_stream.py` 拆成四层

当前单文件职责过多，建议拆成：

1. `frame_source`
   - 负责摄像头/视频流读取
   - 负责断流与关闭
2. `inference_scheduler`
   - 负责检测/识别/情绪的节流与异步调度
3. `track_state`
   - 负责 `track_id`、平滑、身份保持、结果稳定
4. `event_sink`
   - 负责把观察结果交给后端 service，再决定是否写库和告警

对应任务：

- Task-03：检测/识别能力
- Task-04：情绪能力
- Task-05：采集/调度/输出节奏
- Task-07：异常、降级、观测性

### 4.2 将当前 UI 行为映射为 API

| 当前 UI 行为 | 未来 API | 前端页 |
| --- | --- | --- |
| 登录 | `POST /api/auth/login` | 登录页 |
| 查看系统状态 | `GET /api/system/status` | 监控页/系统页 |
| 读取摄像头配置 | `GET /api/cameras` | 监控页 |
| 启动/停止视频源 | `POST /api/cameras/start` / `POST /api/cameras/stop` | 监控页 |
| 查看日志 | `GET /api/logs` | 日志页 |
| 查看考勤 | `GET /api/attendance` | 考勤页 |
| 删除用户 | `DELETE /api/faces/{name}` | 人脸库页 |
| 开始录入/更新模型 | `POST /api/faces/register` / `POST /api/models/train` | 人脸库页 |

## 5. 分阶段计划

### 阶段 0：契约冻结

负责人：

- Task-00

产物：

- `architecture_baseline.md`
- `migration_map.md`
- `api_contract.yaml`
- `event_schema.md`
- `change_request_log.md`

### 阶段 1：并行开发

负责人：

- Task-01
- Task-02
- Task-03
- Task-04
- Task-05
- Task-06
- Task-07
- Task-09

硬规则：

- 只改各自任务目录
- 不动主工程
- 输出必须兼容 Task-00 契约命名

### 阶段 2：统一集成

负责人：

- Task-08

工作内容：

- 把 Task-01 ~ Task-07 的结果接起来
- 决定 legacy 模式是否保留
- 决定新启动入口与打包方式
- 必要时才修改主工程

### 阶段 3：回归与基准

负责人：

- Task-09

目标：

- 校验旧基线未被破坏
- 校验新系统符合契约
- 输出发布门禁材料

## 6. 数据与存储迁移建议

### 6.1 当前必须兼容的遗留数据

- `config/configwin1.txt` ~ `config/configwin4.txt`
- `config/totalUser.txt`
- `config/idlists.txt`
- `config/userdic.txt`
- `data/` 下的人脸样本目录
- `model/model.yml`
- `recognition_logs`
- `attendance_records`

### 6.2 并行阶段建议

- 新模块可以读取这些遗留结构做兼容导入。
- 新模块不要直接改写这些遗留结构，除非该改写发生在各自任务目录内的镜像/适配层。
- 主工程目录内的实际回写由 Task-08 统一处理。

### 6.3 模型文件迁移建议

因为当前 `model.yml` 可能承载两种完全不同的内容：

- LBPH：OpenCV model 文件
- deep/lite：`npz` embedding gallery

建议最终形态：

- 对外通过 `backend_mode` + `model_format` 显式暴露
- 集成阶段允许引入更清晰的新文件名
- 但必须保留对旧 `model.yml` 的兼容读取

## 7. 集成阶段修改权限

### 7.1 允许修改主工程的人

- 只有 Task-08

### 7.2 不允许修改主工程的人

- Task-00
- Task-01
- Task-02
- Task-03
- Task-04
- Task-05
- Task-06
- Task-07
- Task-09

### 7.3 主工程变更前提

满足以下条件后，Task-08 才能改主工程：

1. 本目录契约已经存在且被引用。
2. 相关变更若影响公共边界，已经登记到 `change_request_log.md`。
3. Task-09 能对集成结果做回归。

## 8. 对 Task-01 ~ Task-09 的具体建议

- Task-01：优先做 adapter，不要重写识别算法。
- Task-02：优先围绕契约做交互稿和页面，不要等待主工程改造完成。
- Task-03：输出必须稳定提供 `bbox/track_id/name/confidence/similarity/match_reason`。
- Task-04：即便新增模型，也要兼容 `emotion/confidence/quality/reason`。
- Task-05：不要把“显示逻辑”继续和“持久化逻辑”绑死。
- Task-06：新功能尽量消费现成的 `VisionObservation`，少造侧向接口。
- Task-07：把降级和异常显式建模成状态或告警，而不是打印日志了事。
- Task-08：若要回接旧工程，先做薄适配，不要把所有并行成果硬塞回原来的 Qt 窗口文件。
- Task-09：围绕契约做 smoke test，会比围绕实现细节更稳。
