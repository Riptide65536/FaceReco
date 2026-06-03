# Task-02 Frontend Web

这是多摄像头人脸识别系统的新版 Web 前端原型，只修改 `parallel_work/task-02-frontend-web/`，不触碰主工程 PySide2 代码。目标是把旧桌面工具界面升级为更像完整产品的前后端分离控制台。

## 技术栈

- React 19 + TypeScript
- Vite
- React Router
- 自研轻量 API 适配层，支持 `mock` / `live` / `auto`

## 启动与构建

```powershell
npm install
npm run dev
npm run build
npm run test:mock
```

默认开发服务由 Vite 输出地址。mock 登录账号：

- `admin / FaceReco2026!`
- `operator / monitor2026`

## 接口模式

通过环境变量控制：

```powershell
$env:VITE_API_MODE="mock"  # mock | live | auto
$env:VITE_API_BASE_URL="http://127.0.0.1:18080"
$env:VITE_WS_BASE_URL="ws://127.0.0.1:18080"
npm run dev
```

`auto` 模式下，如果 live API 调用失败，会回退到 mock 数据，便于后端未完全启动时继续评审 UI。

## 页面结构

- `/login`：产品化登录页，展示系统定位、演示账号和当前 API 模式。
- `/overview`：监控总览页，突出 4 路视频矩阵、识别动态、最新日志和系统快照。
- `/cameras`：摄像头管理页，支持搜索、选择、启停、状态与性能信息展示。
- `/faces`：人脸库管理页，展示档案质量、样本数、标签、重点关注状态，并提供演示录入/删除入口。
- `/logs`：日志与考勤页，支持关键字、状态、考勤类型和日期筛选。
- `/system`：系统状态页，展示资源占用、服务健康、摄像头运行面、接口支持矩阵和未完成风险。

## 后端对接说明

参考来源：

- `parallel_work/task-00-contracts/api_contract.yaml`
- `parallel_work/task-00-contracts/event_schema.md`
- `parallel_work/task-01-backend-api/openapi.json`

当前前端的 live 适配层在 `src/lib/api/liveApi.ts`，会把 Task-01 的响应归一化成页面内部类型：

- `POST /api/auth/login`：兼容 `access_token` 和 `token`。
- `GET /api/system/status`：把 Task-01 的 `recognition_backend_mode`、`recognition_provider`、`total_users`、`configured_cameras` 等映射为 UI 状态。
- `GET /api/cameras`：兼容 Task-01 的数组返回和 Task-00 的 `{ items }` 返回。
- `POST /api/cameras/start`、`POST /api/cameras/stop`：默认发送 `{ camera_id }`。
- `GET /api/logs`：兼容 Task-01 的分页 `{ items, total, page, page_size }`。
- `GET /api/attendance`：兼容 Task-01 的 `{ items, total }` 和 Task-00 的 `{ items, summary }`。
- `GET /api/faces`：按 Task-01 OpenAPI 接入，并转换为人脸档案卡片。
- `DELETE /api/faces/{name}`：已预留真实调用。
- `WS /ws/events`：兼容 Task-00 `EventEnvelope` 与普通事件对象。
- `WS /ws/stream/{camera_id}`：兼容 `image`、`image_base64`、`image_data`，并自动追加 `?token=...`。

## 尚未完全联通

- `POST /api/faces/register`：Task-01 需要 base64 图片数组；当前页面没有真实文件上传/摄像头采样流程，只发送占位样本用于联调演示。
- Task-00 与 Task-01 在登录、摄像头、系统状态字段上仍有差异，前端已兼容，但 Task-08 集成时建议统一契约。
- 考勤导出接口未冻结，前端仅做查询和展示。

## 设计方向

视觉上采用深色安防指挥舱风格：青蓝扫描感、琥珀告警强调、玻璃态面板、视频区域优先、状态卡片分层。界面支持加载、空状态、错误提示和较小窗口响应式布局，避免普通白底模板感。
