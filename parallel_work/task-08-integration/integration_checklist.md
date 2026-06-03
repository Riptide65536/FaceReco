# Integration Checklist

## 启动前

- `Task-00-contracts` 已可读，接口边界无新增未登记变更
- `Task-01-backend-api/main.py` 存在
- `Task-02-frontend-web/package.json` 存在
- `D:/Anaconda_envs/envs/FaceReco/python.exe` 可用
- `node`、`npm` 可用
- 运行过 `python parallel_work/task-08-integration/preflight_check.py`

## 第一次联调顺序

1. 运行 `python parallel_work/task-08-integration/start_all.py`
2. 等待后端健康检查通过
3. 打开 `http://127.0.0.1:5173`
4. 登录并确认总览页可打开
5. 检查 `系统状态`、`摄像头列表`、`日志`、`考勤`、`人脸库`
6. 在摄像头管理页尝试启动已有视频源槽位
7. 若联调失败，切到 `python parallel_work/task-08-integration/start_legacy_pyside.py`

## 演示最小通过条件

- 前端能打开并完成登录
- 后端 `GET /api/health` 正常
- `GET /api/system/status` 正常
- `GET /api/cameras` 正常
- `GET /api/logs` 正常
- `GET /api/attendance` 正常
- `GET /api/faces` 正常
- 至少一条摄像头源可以完成启停预演

## 当前依赖任务

- 强依赖：`task-00-contracts`
- 强依赖：`task-01-backend-api`
- 强依赖：`task-02-frontend-web`
- 暂未接入：`task-03` ~ `task-07`

## 当前已知风险

- Task-01 后端冷启动慢
- 摄像头启停依赖 legacy 槽位配置
- 新前端仍未提供完整的视频源编辑能力
- 当前仍是“集成脚手架版”，不是回接主工程入口后的最终形态

## 回退策略

- Web 版失败：停掉 `start_all.py`
- 启动兜底：`python parallel_work/task-08-integration/start_legacy_pyside.py`
