import { createMockFrame } from "./mockFrames";
import type {
  ActionResult,
  AttendanceFilters,
  AttendanceRecord,
  AuthCredentials,
  AuthSession,
  BackendApi,
  CameraSummary,
  FaceProfile,
  FaceRegistrationPayload,
  LogFilters,
  LogRecord,
  StreamFrame,
  SystemStatus,
  UiEvent,
} from "./types";

const demoUsers = {
  admin: {
    password: "FaceReco2026!",
    id: "u-admin",
    name: "总控管理员",
    role: "Admin",
  },
  operator: {
    password: "monitor2026",
    id: "u-ops",
    name: "监控专员",
    role: "Operator",
  },
};

const cameraState: CameraSummary[] = [
  {
    camera_id: "cam-lobby",
    name: "大厅主入口",
    location: "一层门禁大厅",
    source: "rtsp://demo/lobby",
    status: "online",
    runtime_mode: "realtime",
    display_mode: "recognition",
    fps: 24.8,
    latency_ms: 138,
    faces: 3,
    alert_count: 0,
    last_event_at: new Date(Date.now() - 2 * 60_000).toISOString(),
    resolution: "1920x1080",
    provider: "ArcFace / YOLOv8-face",
    preview_hint: "人流高峰，优先保证视频流畅度。",
  },
  {
    camera_id: "cam-east-gate",
    name: "东侧通道",
    location: "二层办公通道",
    source: "rtsp://demo/east-gate",
    status: "warning",
    runtime_mode: "balanced",
    display_mode: "standard",
    fps: 18.6,
    latency_ms: 186,
    faces: 1,
    alert_count: 2,
    last_event_at: new Date(Date.now() - 7 * 60_000).toISOString(),
    resolution: "1280x720",
    provider: "ArcFace / YOLOv8-face",
    preview_hint: "检测到逆光，建议调整补光或阈值。",
  },
  {
    camera_id: "cam-lab",
    name: "实验室门口",
    location: "三层研发实验室",
    source: "rtsp://demo/lab",
    status: "online",
    runtime_mode: "accurate",
    display_mode: "recognition",
    fps: 15.2,
    latency_ms: 244,
    faces: 2,
    alert_count: 1,
    last_event_at: new Date(Date.now() - 4 * 60_000).toISOString(),
    resolution: "1920x1080",
    provider: "ArcFace / YOLOv8-face",
    preview_hint: "高精度模式已开启，适合门禁核验。",
  },
  {
    camera_id: "cam-archive",
    name: "档案室",
    location: "地下库房入口",
    source: "rtsp://demo/archive",
    status: "idle",
    runtime_mode: "balanced",
    display_mode: "signal",
    fps: 0,
    latency_ms: 0,
    faces: 0,
    alert_count: 0,
    last_event_at: new Date(Date.now() - 38 * 60_000).toISOString(),
    resolution: "1280x720",
    provider: "ArcFace / YOLOv8-face",
    preview_hint: "当前未启动，可在摄像头管理页恢复。",
  },
];

let faceState: FaceProfile[] = [
  {
    id: "face-001",
    name: "陈琳",
    department: "安保部",
    sample_count: 18,
    quality: "excellent",
    watchlist: false,
    last_seen_at: new Date(Date.now() - 18 * 60_000).toISOString(),
    tags: ["门禁常驻", "高质量样本"],
    avatar_seed: "chenlin",
  },
  {
    id: "face-002",
    name: "王锐",
    department: "研发中心",
    sample_count: 9,
    quality: "good",
    watchlist: false,
    last_seen_at: new Date(Date.now() - 54 * 60_000).toISOString(),
    tags: ["研发", "实验室"],
    avatar_seed: "wangrui",
  },
  {
    id: "face-003",
    name: "赵越",
    department: "访客管理",
    sample_count: 6,
    quality: "warning",
    watchlist: true,
    last_seen_at: new Date(Date.now() - 6 * 60_000).toISOString(),
    tags: ["重点关注", "遮挡较多"],
    avatar_seed: "zhaoyue",
  },
  {
    id: "face-004",
    name: "李珺",
    department: "行政部",
    sample_count: 12,
    quality: "good",
    watchlist: false,
    last_seen_at: new Date(Date.now() - 84 * 60_000).toISOString(),
    tags: ["考勤稳定"],
    avatar_seed: "lijun",
  },
];

const logState: LogRecord[] = [
  {
    id: "log-1001",
    person_name: "陈琳",
    location: "一层门禁大厅",
    captured_at: new Date(Date.now() - 8 * 60_000).toISOString(),
    emotion: "neutral",
    attendance_type: "上班打卡",
    status: "正常",
    similarity: 0.96,
    confidence: 0.93,
    camera_id: "cam-lobby",
  },
  {
    id: "log-1002",
    person_name: "赵越",
    location: "二层办公通道",
    captured_at: new Date(Date.now() - 16 * 60_000).toISOString(),
    emotion: "serious",
    attendance_type: "外出登记",
    status: "已记录",
    similarity: 0.89,
    confidence: 0.81,
    camera_id: "cam-east-gate",
  },
  {
    id: "log-1003",
    person_name: "王锐",
    location: "三层研发实验室",
    captured_at: new Date(Date.now() - 24 * 60_000).toISOString(),
    emotion: "happy",
    attendance_type: "上班打卡",
    status: "正常",
    similarity: 0.93,
    confidence: 0.91,
    camera_id: "cam-lab",
  },
  {
    id: "log-1004",
    person_name: "陌生人",
    location: "二层办公通道",
    captured_at: new Date(Date.now() - 31 * 60_000).toISOString(),
    emotion: "unknown",
    attendance_type: "未识别",
    status: "异常",
    similarity: 0.42,
    confidence: 0.51,
    camera_id: "cam-east-gate",
  },
  {
    id: "log-1005",
    person_name: "李珺",
    location: "一层门禁大厅",
    captured_at: new Date(Date.now() - 45 * 60_000).toISOString(),
    emotion: "neutral",
    attendance_type: "外出登记",
    status: "已记录",
    similarity: 0.91,
    confidence: 0.88,
    camera_id: "cam-lobby",
  },
  {
    id: "log-1006",
    person_name: "陈琳",
    location: "地下库房入口",
    captured_at: new Date(Date.now() - 98 * 60_000).toISOString(),
    emotion: "neutral",
    attendance_type: "重复识别",
    status: "已记录",
    similarity: 0.94,
    confidence: 0.9,
    camera_id: "cam-archive",
  },
];

const attendanceState: AttendanceRecord[] = [
  {
    id: "att-001",
    name: "陈琳",
    date: "2026-06-03",
    first_seen_at: "2026-06-03T08:04:00+08:00",
    last_seen_at: "2026-06-03T17:38:00+08:00",
    status: "正常",
    attendance_type: "上班打卡",
    location: "一层门禁大厅",
  },
  {
    id: "att-002",
    name: "王锐",
    date: "2026-06-03",
    first_seen_at: "2026-06-03T08:26:00+08:00",
    last_seen_at: "2026-06-03T18:01:00+08:00",
    status: "正常",
    attendance_type: "上班打卡",
    location: "三层研发实验室",
  },
  {
    id: "att-003",
    name: "赵越",
    date: "2026-06-03",
    first_seen_at: "2026-06-03T09:11:00+08:00",
    last_seen_at: "2026-06-03T09:11:00+08:00",
    status: "迟到",
    attendance_type: "上班打卡",
    location: "二层办公通道",
  },
  {
    id: "att-004",
    name: "李珺",
    date: "2026-06-03",
    first_seen_at: "2026-06-03T08:14:00+08:00",
    last_seen_at: "2026-06-03T16:48:00+08:00",
    status: "早退",
    attendance_type: "下班打卡",
    location: "一层门禁大厅",
  },
];

let frameCounter = 0;
let eventCounter = 0;

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function delay(ms = 260) {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, ms);
  });
}

function calculateSystemStatus(): SystemStatus {
  const activeCameras = cameraState.filter(
    (camera) => camera.status === "online" || camera.status === "warning",
  );
  const totalAlerts = cameraState.reduce(
    (count, camera) => count + camera.alert_count,
    0,
  );
  const hasDegraded = cameraState.some(
    (camera) => camera.status === "warning" || camera.status === "offline",
  );

  return {
    overall: hasDegraded ? "degraded" : "healthy",
    uptime: "5 天 11 小时",
    cpu_percent: 46.8,
    gpu_percent: 61.2,
    memory_percent: 58.1,
    temperature_c: 63.5,
    active_cameras: activeCameras.length,
    total_cameras: cameraState.length,
    total_faces: faceState.length,
    pending_model_update: faceState.some((face) => face.quality === "warning"),
    backend_mode: activeCameras.some((camera) => camera.runtime_mode === "accurate")
      ? "balanced + accurate mix"
      : "realtime first",
    provider: "YOLOv8-face + ArcFace + Emotion Model",
    queue_backlog: totalAlerts > 0 ? 3 : 1,
    last_sync_at: new Date().toISOString(),
    inference: {
      avg_latency_ms: 178,
      recognition_fps: 19.4,
      dropped_frames: 4,
      unknown_rate: 0.07,
    },
    services: [
      {
        name: "Recognition Pipeline",
        state: hasDegraded ? "degraded" : "healthy",
        message: hasDegraded
          ? "通道 2 存在逆光，识别置信度轻微波动。"
          : "识别链路稳定运行中。",
        latency_ms: 186,
        updated_at: new Date().toISOString(),
      },
      {
        name: "Camera Runtime",
        state: "healthy",
        message: "视频流与主界面刷新均已上线。",
        latency_ms: 92,
        updated_at: new Date().toISOString(),
      },
      {
        name: "Attendance Service",
        state: "healthy",
        message: "考勤状态正常回填。",
        latency_ms: 74,
        updated_at: new Date().toISOString(),
      },
      {
        name: "Face Registry",
        state: faceState.some((face) => face.quality === "warning")
          ? "degraded"
          : "healthy",
        message: faceState.some((face) => face.quality === "warning")
          ? "存在样本质量偏低人员，建议补采。"
          : "样本库质量稳定。",
        latency_ms: 48,
        updated_at: new Date().toISOString(),
      },
    ],
  };
}

function matchesFuzzy(
  value: string,
  candidate: string | undefined,
  allowAnyText = new Set(["", "任何地点", "任何人员", "任何状态", "任何类型"]),
) {
  if (!candidate || allowAnyText.has(candidate)) {
    return true;
  }
  return value.toLowerCase().includes(candidate.toLowerCase());
}

function withinTimeRange(value: string, start?: string, end?: string) {
  const time = new Date(value).getTime();
  if (start && time < new Date(start).getTime()) {
    return false;
  }
  if (end && time > new Date(end).getTime() + 24 * 60 * 60 * 1000) {
    return false;
  }
  return true;
}

function nextEvent(): UiEvent {
  const camera = cameraState[eventCounter % cameraState.length];
  const face = faceState[eventCounter % faceState.length];
  const eventTemplates: Omit<UiEvent, "id" | "camera_id" | "frame_id" | "timestamp">[] = [
    {
      type: "recognition",
      title: `${face.name} 识别通过`,
      description: `${camera.location} 完成身份校验，情绪稳定。`,
      severity: "success",
      person_name: face.name,
      emotion: "neutral",
    },
    {
      type: "alert",
      title: "陌生人连续出现",
      description: `${camera.name} 连续 3 帧检测到未注册对象。`,
      severity: "warning",
      emotion: "unknown",
    },
    {
      type: "status",
      title: "运行模式切换建议",
      description: `${camera.name} 当前适合切回平衡模式。`,
      severity: "info",
    },
    {
      type: "alert",
      title: "重点关注对象命中",
      description: `${face.name} 在 ${camera.location} 被再次识别。`,
      severity: face.watchlist ? "critical" : "warning",
      person_name: face.name,
      emotion: "serious",
    },
  ];

  const template = eventTemplates[eventCounter % eventTemplates.length];
  eventCounter += 1;

  return {
    ...template,
    id: `event-${eventCounter}`,
    camera_id: camera.camera_id,
    frame_id: 1000 + eventCounter,
    timestamp: new Date().toISOString(),
  };
}

function buildActionResult(message: string): ActionResult {
  return { success: true, message };
}

export const mockApi: BackendApi = {
  async login(credentials: AuthCredentials) {
    await delay();
    const account = demoUsers[credentials.username as keyof typeof demoUsers];
    if (!account || account.password !== credentials.password) {
      throw new Error(
        "登录失败。可使用 admin / FaceReco2026! 或 operator / monitor2026。",
      );
    }
    const session: AuthSession = {
      token: `mock-token-${account.id}`,
      expires_at: new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString(),
      user: {
        id: account.id,
        name: account.name,
        role: account.role,
        last_login_at: new Date().toISOString(),
      },
    };
    return session;
  },

  async getSystemStatus() {
    await delay(200);
    return calculateSystemStatus();
  },

  async getCameras() {
    await delay(180);
    return deepClone(cameraState);
  },

  async startCamera(cameraId: string) {
    await delay(220);
    const target = cameraState.find((camera) => camera.camera_id === cameraId);
    if (!target) {
      throw new Error(`未找到摄像头 ${cameraId}`);
    }
    target.status = "online";
    target.fps = 20.8;
    target.latency_ms = 156;
    target.last_event_at = new Date().toISOString();
    return buildActionResult(`已启动 ${target.name}`);
  },

  async stopCamera(cameraId: string) {
    await delay(220);
    const target = cameraState.find((camera) => camera.camera_id === cameraId);
    if (!target) {
      throw new Error(`未找到摄像头 ${cameraId}`);
    }
    target.status = "idle";
    target.fps = 0;
    target.latency_ms = 0;
    target.faces = 0;
    target.last_event_at = new Date().toISOString();
    return buildActionResult(`已停止 ${target.name}`);
  },

  async getLogs(filters: LogFilters) {
    await delay(180);
    const filtered = logState.filter((record) => {
      const searchSpace = [
        record.person_name,
        record.location,
        record.emotion,
        record.status,
      ].join(" ");
      return (
        matchesFuzzy(record.person_name, filters.name) &&
        matchesFuzzy(record.location, filters.location) &&
        matchesFuzzy(record.status, filters.status) &&
        matchesFuzzy(record.attendance_type, filters.attendance_type) &&
        matchesFuzzy(searchSpace, filters.search, new Set([""])) &&
        withinTimeRange(record.captured_at, filters.start_time, filters.end_time)
      );
    });
    return deepClone(filtered);
  },

  async getAttendance(filters: AttendanceFilters) {
    await delay(180);
    const filtered = attendanceState.filter((record) => {
      const searchSpace = [record.name, record.location, record.status].join(" ");
      return (
        matchesFuzzy(record.status, filters.status) &&
        matchesFuzzy(searchSpace, filters.search, new Set([""])) &&
        withinTimeRange(record.date, filters.start_time, filters.end_time)
      );
    });
    return deepClone(filtered);
  },

  async getFaceLibrary() {
    await delay(220);
    return deepClone(faceState);
  },

  async registerFace(payload: FaceRegistrationPayload) {
    await delay(260);
    const profile: FaceProfile = {
      id: `face-${Date.now()}`,
      name: payload.name,
      department: payload.department,
      sample_count: 4,
      quality: "good",
      watchlist: false,
      last_seen_at: new Date().toISOString(),
      tags: payload.tags,
      avatar_seed: payload.name.toLowerCase(),
    };
    faceState = [profile, ...faceState];
    return buildActionResult(`已新增示例人员 ${payload.name}`);
  },

  async deleteFace(name: string) {
    await delay(220);
    faceState = faceState.filter((profile) => profile.name !== name);
    return buildActionResult(`已删除 ${name}`);
  },

  connectEvents(onMessage) {
    const firstTick = globalThis.setTimeout(() => {
      onMessage(nextEvent());
    }, 420);
    const timer = globalThis.setInterval(() => {
      onMessage(nextEvent());
    }, 5400);
    return () => {
      globalThis.clearTimeout(firstTick);
      globalThis.clearInterval(timer);
    };
  },

  connectStream(cameraId, onMessage) {
    const camera =
      cameraState.find((item) => item.camera_id === cameraId) ?? cameraState[0];

    const emitFrame = () => {
      frameCounter += 1;
      const severity =
        camera.status === "warning"
          ? "warning"
          : camera.status === "online"
            ? "success"
            : "info";
      const frame: StreamFrame = {
        camera_id: camera.camera_id,
        frame_id: frameCounter,
        timestamp: new Date().toISOString(),
        image: createMockFrame(
          camera,
          frameCounter,
          camera.status === "idle" ? "IDLE MODE" : `${camera.fps.toFixed(1)} FPS`,
          severity,
        ),
      };
      onMessage(frame);
    };

    const firstTick = globalThis.setTimeout(emitFrame, 100);
    const timer = globalThis.setInterval(emitFrame, 1250);

    return () => {
      globalThis.clearTimeout(firstTick);
      globalThis.clearInterval(timer);
    };
  },
};
