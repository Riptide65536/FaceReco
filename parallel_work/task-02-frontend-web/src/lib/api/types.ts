export type ApiMode = "auto" | "mock" | "live";
export type HealthState = "healthy" | "degraded" | "offline";
export type CameraStatus =
  | "online"
  | "idle"
  | "offline"
  | "warning"
  | "starting";
export type Severity = "info" | "success" | "warning" | "critical";
export type RuntimeMode = "realtime" | "balanced" | "accurate";

export interface AuthCredentials {
  username: string;
  password: string;
}

export interface AuthSession {
  token: string;
  expires_at: string;
  user: {
    id: string;
    name: string;
    role: string;
    last_login_at: string;
  };
}

export interface ActionResult {
  success: boolean;
  message: string;
}

export interface CameraSummary {
  camera_id: string;
  name: string;
  location: string;
  source: string;
  status: CameraStatus;
  runtime_mode: RuntimeMode;
  display_mode: "standard" | "recognition" | "signal";
  fps: number;
  latency_ms: number;
  faces: number;
  alert_count: number;
  last_event_at: string;
  resolution: string;
  provider: string;
  preview_hint: string;
}

export interface ServiceHealth {
  name: string;
  state: HealthState;
  message: string;
  latency_ms: number;
  updated_at: string;
}

export interface SystemStatus {
  overall: HealthState;
  uptime: string;
  cpu_percent: number;
  gpu_percent: number;
  memory_percent: number;
  temperature_c: number;
  active_cameras: number;
  total_cameras: number;
  total_faces: number;
  pending_model_update: boolean;
  backend_mode: string;
  provider: string;
  queue_backlog: number;
  last_sync_at: string;
  inference: {
    avg_latency_ms: number;
    recognition_fps: number;
    dropped_frames: number;
    unknown_rate: number;
  };
  services: ServiceHealth[];
}

export interface LogFilters {
  name?: string;
  location?: string;
  status?: string;
  attendance_type?: string;
  search?: string;
  start_time?: string;
  end_time?: string;
}

export interface AttendanceFilters {
  search?: string;
  status?: string;
  start_time?: string;
  end_time?: string;
}

export interface LogRecord {
  id: string;
  person_name: string;
  location: string;
  captured_at: string;
  emotion: string;
  attendance_type: string;
  status: string;
  similarity: number;
  confidence: number;
  camera_id: string;
}

export interface AttendanceRecord {
  id: string;
  name: string;
  date: string;
  first_seen_at: string;
  last_seen_at: string;
  status: string;
  attendance_type: string;
  location: string;
}

export interface FaceProfile {
  id: string;
  name: string;
  department: string;
  sample_count: number;
  quality: "excellent" | "good" | "warning";
  watchlist: boolean;
  last_seen_at: string;
  tags: string[];
  avatar_seed: string;
}

export interface FaceRegistrationPayload {
  name: string;
  department: string;
  tags: string[];
}

export interface UiEvent {
  id: string;
  camera_id: string;
  frame_id: number;
  timestamp: string;
  type: "recognition" | "alert" | "status";
  title: string;
  description: string;
  severity: Severity;
  person_name?: string;
  emotion?: string;
}

export interface StreamFrame {
  camera_id: string;
  frame_id: number;
  timestamp: string;
  image: string;
}

export interface BackendApi {
  login: (credentials: AuthCredentials) => Promise<AuthSession>;
  getSystemStatus: () => Promise<SystemStatus>;
  getCameras: () => Promise<CameraSummary[]>;
  startCamera: (cameraId: string) => Promise<ActionResult>;
  stopCamera: (cameraId: string) => Promise<ActionResult>;
  getLogs: (filters: LogFilters) => Promise<LogRecord[]>;
  getAttendance: (filters: AttendanceFilters) => Promise<AttendanceRecord[]>;
  getFaceLibrary: () => Promise<FaceProfile[]>;
  registerFace: (payload: FaceRegistrationPayload) => Promise<ActionResult>;
  deleteFace: (name: string) => Promise<ActionResult>;
  connectEvents: (
    onMessage: (event: UiEvent) => void,
    onError?: (error: Error) => void,
  ) => () => void;
  connectStream: (
    cameraId: string,
    onMessage: (frame: StreamFrame) => void,
    onError?: (error: Error) => void,
  ) => () => void;
}
