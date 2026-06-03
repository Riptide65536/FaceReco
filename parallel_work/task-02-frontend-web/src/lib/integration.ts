export interface ContractSupportItem {
  label: string;
  method: string;
  path: string;
  support: "ready" | "mock-only" | "pending";
  note: string;
}

export const contractSupportItems: ContractSupportItem[] = [
  {
    label: "用户登录",
    method: "POST",
    path: "/api/auth/login",
    support: "ready",
    note: "前端已接入 live/mock 双模式。",
  },
  {
    label: "系统状态",
    method: "GET",
    path: "/api/system/status",
    support: "ready",
    note: "总览页与系统状态页都依赖此接口。",
  },
  {
    label: "摄像头列表",
    method: "GET",
    path: "/api/cameras",
    support: "ready",
    note: "用于总览页与摄像头管理页。",
  },
  {
    label: "启停摄像头",
    method: "POST",
    path: "/api/cameras/start|stop",
    support: "ready",
    note: "前端默认发送 { camera_id }。",
  },
  {
    label: "日志查询",
    method: "GET",
    path: "/api/logs",
    support: "ready",
    note: "支持按人员、地点、状态、时间过滤。",
  },
  {
    label: "考勤查询",
    method: "GET",
    path: "/api/attendance",
    support: "ready",
    note: "日志与考勤页直接消费。",
  },
  {
    label: "人脸库列表",
    method: "GET",
    path: "/api/faces",
    support: "ready",
    note: "Task-01 OpenAPI 已提供列表接口，前端会归一化为 FaceProfile。",
  },
  {
    label: "登记人脸",
    method: "POST",
    path: "/api/faces/register",
    support: "mock-only",
    note: "Task-01 需要 base64 样本数组；当前 UI 表单仅发送占位样本用于联调演示。",
  },
  {
    label: "删除人脸",
    method: "DELETE",
    path: "/api/faces/{name}",
    support: "ready",
    note: "mock/live 都已预留调用入口。",
  },
  {
    label: "事件总线",
    method: "WS",
    path: "/ws/events",
    support: "ready",
    note: "前端支持事件流回退到 mock。",
  },
  {
    label: "视频流",
    method: "WS",
    path: "/ws/stream/{camera_id}",
    support: "ready",
    note: "前端按 FramePacket.image 解码，若无图片则显示占位状态。",
  },
];

export const pendingIntegrationGaps = [
  "POST /api/faces/register 已按 Task-01 base64 样本字段预留，但当前页面没有真实文件选择/采样流程，只发送占位样本做联调演示。",
  "Task-00 与 Task-01 的登录返回字段不同：Task-00 为 token，Task-01 为 access_token；前端已做兼容映射，Task-08 集成时建议统一。",
  "Task-00 与 Task-01 的 SystemStatus/Camera 字段不同；前端适配层已归一化，但最终集成最好收敛到同一契约。",
  "WS /ws/stream/{camera_id} 已兼容 image/image_base64/image_data；真实图片编码格式仍建议由 Task-01 在文档中固定为 base64 JPEG 或 data URL。",
  "考勤导出接口未冻结，当前前端仅展示筛选与表格，不直接触发真实文件下载。",
];
