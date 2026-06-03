# Task-08 Integration

本目录提供当前阶段的最小集成脚手架，目标是先把 `Task-02` 新前端、`Task-01` 后端入口和旧工程的人脸识别/数据机制拼成一个可启动、可联调、可演示的基础版本，同时不改动主工程源码。

## 当前集成结论

- 前端使用 `parallel_work/task-02-frontend-web/`
- 后端入口使用 `parallel_work/task-01-backend-api/main.py`
- 识别、情绪、日志、数据库仍复用旧工程 `app/`、`services/`、`sqls.py`
- PySide2 桌面版保留为保底入口，通过本目录脚本单独启动
- 主工程文件未改动，当前所有新增内容都只在 `parallel_work/task-08-integration/`

## 目录说明

- `config.json`：统一启动配置，显式指定 FaceReco Python、前后端端口和推荐演示位。
- `common.py`：公共路径、命令、健康检查和请求工具。
- `preflight_check.py`：启动前检查依赖、端口、legacy 摄像头配置。
- `start_backend.py`：用 `FaceReco` 环境启动 Task-01 后端，并等待健康检查通过。
- `start_frontend.py`：用统一环境变量启动 Task-02 前端，支持 `dev` / `preview`。
- `start_all.py`：一键拉起前后端，是当前推荐入口。
- `start_legacy_pyside.py`：启动旧 PySide2 桌面版兜底方案。
- `smoke_test.py`：本地集成预演脚本。
- `integration_checklist.md`：集成清单和联调顺序。
- `minimal_change_plan.md`：后续若接回主工程时的最小改动计划。
- `test_report.md`：本轮自测结果和当前阻塞说明。

## 集成架构

```text
task-08 start_all.py
  -> task-01-backend-api/main.py
     -> legacy AppService / repositories / sqls / recognition pipeline
  -> task-02-frontend-web (Vite dev or preview)
     -> REST / WebSocket -> Task-01 backend

fallback:
task-08 start_legacy_pyside.py
  -> run.py
  -> main.py
  -> 原 PySide2 桌面工程
```

## 启动方式

### 1. 启动前检查

```powershell
python parallel_work/task-08-integration/preflight_check.py
```

说明：

- 这个脚本会检查 `config.json` 中指定的 `FaceReco` Python 是否存在
- 会检查 `PySide2`、`cv2`、`pydantic`、`numpy`
- 会检查 `node`、`npm`
- 会打印当前 legacy 1~4 号摄像头槽位是否已有视频源配置

### 2. 推荐的一键启动

```powershell
python parallel_work/task-08-integration/start_all.py
```

默认行为：

- 后端地址：`http://127.0.0.1:18080`
- 前端地址：`http://127.0.0.1:5173`
- 前端模式：`live`
- 前端运行方式：`dev`

可选：

```powershell
python parallel_work/task-08-integration/start_all.py --frontend-mode preview
python parallel_work/task-08-integration/start_all.py --api-mode auto
```

建议：

- 正式演示优先用 `--frontend-mode preview`
- 联调期优先用默认 `dev`
- 若后端某些接口尚未稳定，可以临时用 `--api-mode auto` 让前端回退到 mock 保持 UI 可展示

### 3. 分开启动

```powershell
python parallel_work/task-08-integration/start_backend.py
python parallel_work/task-08-integration/start_frontend.py --mode dev
```

### 4. PySide2 保底方案

```powershell
python parallel_work/task-08-integration/start_legacy_pyside.py
```

适用场景：

- 新前后端栈联调临时失败
- 现场只需要快速回到旧版可运行桌面程序
- 需要核对旧 UI 与新 Web 版的数据一致性

## 第一次前后端组装流程

1. 运行 `preflight_check.py`
2. 运行 `start_all.py`
3. 打开前端首页，使用后端账号登录
4. 进入摄像头页，优先测试已有视频源的槽位
5. 进入总览、日志、考勤、系统页确认 REST 接口可用
6. 若新栈异常，立即切换到 `start_legacy_pyside.py`

## 依赖哪些任务已完成

- `Task-00-contracts`
  - 负责冻结 REST / WebSocket 边界和迁移规则
- `Task-01-backend-api`
  - 提供当前基础后端入口与 legacy adapter 思路
- `Task-02-frontend-web`
  - 提供可运行的新前端界面

## 当前基础版仍然依赖的旧机制

- `app/services/app_service.py`
- `app/services/recognition_pipeline.py`
- `app/repositories.py`
- `services/face_recognition_service.py`
- `services/emotion_service.py`
- `sqls.py`

## 当前阻塞和限制

- 后端冷启动慢，模型首次加载通常需要 20~60 秒，Task-01 自带 smoke 的 20 秒超时不够。
- 前端当前没有“输入视频源地址”的真实表单，因此摄像头启停仍依赖 legacy 配置文件里已有的槽位信息。
- 当前基础版只完成 `Task-01 + Task-02 + 旧机制` 的最小组合；`Task-03` 之后的优化尚未接入。
- 目前还没有回改主工程入口，Web 版仍通过 `task-08` 脚本单独启动。

## 推荐演示位

- 优先试 `camera_id=2`
  - 当前仓库的 legacy 配置通常已把 2 号槽位指向仓库内示例视频
- 次选 `camera_id=1`
  - 通常对应集成摄像头，但依赖现场硬件

## 后续若接回主工程

见 [minimal_change_plan.md](/d:/Coding_programs/Projects/Facical_reco_base/MultiCameraManagement-FacialRecognition/parallel_work/task-08-integration/minimal_change_plan.md)。
