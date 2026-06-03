# Minimal Change Plan

在你明确要求“开始接回主工程”之前，不修改主工程源码。真正进入回接阶段时，建议按下面顺序做最小化改动。

## 目标

- 不直接重写 `main.py`
- 不破坏 `run.py -> main.py` 的旧桌面基线
- 保持 Web 版和 PySide2 版都能独立回退

## 最小改动方案

1. 根目录新增一个非常薄的 Web 启动入口
   - 例如 `run_web.py` 或 `run_web.bat`
   - 只负责转调 `parallel_work/task-08-integration/start_all.py`

2. 根目录 README 增加双入口说明
   - `python run.py`：旧桌面版
   - `python run_web.py`：新前后端版

3. 若必须从桌面端跳转 Web
   - 仅在登录窗口或工具菜单新增“打开 Web 控制台”按钮
   - 不改识别链、数据链、数据库链

4. 统一配置时优先新增，而不是替换
   - 新增 `config/web_runtime.json` 或 `.env.web`
   - 不直接覆盖旧 `configwin*.txt`

## 明确避免的改动

- 不并行重写 `app/runtime/camera_stream.py`
- 不把 Task-02 资源直接塞进 `ui/`
- 不把 Task-01 代码散改到 `app/`、`services/`、`core/`
- 不修改旧工程识别链路的默认入口，除非 Task-03 之后已稳定

## 回退方式

- 删掉新增的 `run_web.py` 或 `run_web.bat`
- 保留 `parallel_work/task-08-integration/` 不动
- 继续使用 `python run.py`
