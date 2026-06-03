# Task-08 Test Report

测试日期：2026-06-04

## 测试目标

- 验证 `task-08` 脚手架可以在不改主工程源码的前提下，拉起 `Task-02` 新前端和 `Task-01` 后端
- 验证启动脚本显式使用 `FaceReco` Python，而不是当前 shell 默认 Python
- 至少完成一次本地集成预演

## 本轮执行

### 1. 读取并核对并行任务产物

- 已核对 `prompt.md`
- 已核对 `prompt_new.md`
- 已核对 `parallel_work/task-00-contracts/`
- 已核对 `parallel_work/task-01-backend-api/`
- 已核对 `parallel_work/task-02-frontend-web/`

### 2. 环境核对

- 默认 `python` 为 `3.14.5`
- `FaceReco` 环境为 `D:\Anaconda_envs\envs\FaceReco\python.exe`
- `FaceReco` 环境中确认存在：
  - `PySide2`
  - `cv2`
  - `pydantic`
  - `numpy`
- Node.js：`v24.15.0`
- npm：`11.12.1`

### 3. 已执行命令

```powershell
python parallel_work/task-08-integration/preflight_check.py
```

预期：

- 检查 `FaceReco` Python
- 检查前后端目录
- 检查 Node/npm
- 检查 legacy 槽位配置

```powershell
D:\Anaconda_envs\envs\FaceReco\python.exe -m pytest -q parallel_work/task-01-backend-api/tests/test_openapi.py
```

结果：

- 通过，`1 passed`

```powershell
npm run build
```

工作目录：

- `parallel_work/task-02-frontend-web/`

结果：

- 通过，Vite build 成功

```powershell
npm run test:mock
```

工作目录：

- `parallel_work/task-02-frontend-web/`

结果：

- 通过，mock 登录、状态、摄像头、日志、考勤、人脸库均返回

```powershell
python parallel_work/task-08-integration/smoke_test.py
```

结果：

- 通过
- 前端 build 成功
- 后端在 `http://127.0.0.1:18090` 拉起成功
- `POST /api/auth/login`、`GET /api/system/status`、`GET /api/cameras`、`GET /api/logs`、`GET /api/attendance`、`GET /api/faces` 全部通过
- `camera_id=2` 的示例视频源完成一次启动/停止预演

```powershell
python parallel_work/task-08-integration/start_all.py --frontend-mode preview
```

结果：

- 通过后台探测确认
- 后端 `http://127.0.0.1:18080/api/health` 可访问
- 前端 `http://127.0.0.1:5173` 可访问
- 说明 `task-08` 的整栈入口已经具备可演示启动能力

## 本地集成预演结论

- 已完成一次“前端构建 + 后端实际启动 + REST 联调 + 摄像头启停”的本地预演
- 已完成一次 `start_all.py` 整栈拉起验证
- 当前版本满足“先有基本可视化展示”的前置要求
- 当前最关键的集成价值是：
  - 明确固定使用 `FaceReco` Python
  - 给出统一启动入口
  - 给出保底 PySide2 回退入口
  - 给出联调与验收前检查方法

## 当前仍阻塞或未完成项

- `Task-03` ~ `Task-07` 的优化能力尚未接入当前基础版
- 前端仍没有完整的视频源编辑表单，因此摄像头启停依赖 legacy 配置槽位
- Task-01 冷启动时间长，需要 `task-08` 启动器额外等待健康检查
- 当前还没有把 Web 启动入口接回根目录主工程

## 结论

- `task-08` 当前交付的是“集成脚手架 + 启动器 + 联调流程 + 回退方案”
- 在未改主工程源码的约束下，已经能支持下一轮演示与集成推进
