# Task-02 Test Report

测试日期：2026-06-04

## 测试范围

- React/Vite 前端生产构建
- mock API 联调演示
- 页面路由结构核对
- Task-00 / Task-01 接口差异核对

## 执行结果

```powershell
npm run build
```

结果：通过。

摘要：

- TypeScript 编译通过
- Vite production build 成功
- 输出 `dist/index.html` 和静态资源

```powershell
npm run test:mock
```

结果：通过。

输出摘要：

```json
{
  "login": "总控管理员",
  "system": "degraded",
  "cameras": 4,
  "logs": 6,
  "attendance": 4,
  "faces": 4,
  "start": true,
  "stop": true
}
```

## 页面路由核对

- `/login`：已实现
- `/overview`：已实现
- `/cameras`：已实现
- `/faces`：已实现
- `/logs`：已实现
- `/system`：已实现
- `/`：重定向到 `/overview`

## Mock/Live 联调情况

- mock：可登录、可加载系统状态、摄像头、日志、考勤、人脸库，可演示摄像头启停和实时事件/视频预览。
- live：已按 Task-01 OpenAPI 适配主要 REST 接口和 WebSocket 地址/token 规则。
- auto：live 失败时回退 mock，方便后端未启动时继续预览。

## 未完成接口清单

- 真实人脸登记采样流程：页面尚未提供文件选择或从摄像头采样，只按 Task-01 字段发送占位 base64 图片。
- 考勤导出接口：Task-00/Task-01 未冻结，未实现真实导出。
- 契约统一：Task-00 与 Task-01 对 `LoginResponse`、`SystemStatus`、`CameraDescriptor/CameraInfo` 的字段命名不同，目前由前端适配层兜底。

## 风险

- 如果 Task-01 调整字段名但不更新 OpenAPI，live 映射可能需要同步更新。
- WebSocket 消息结构目前做了宽松兼容，最终集成建议固定事件 envelope 和视频图片字段。
- 人脸登记真实流程需要后续补 UI：文件上传、样本质量反馈、采集进度、训练状态。
