import { apiConfig } from "./config";
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

export class UnsupportedContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UnsupportedContractError";
  }
}

function buildQuery(
  path: string,
  params: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  });
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

function normalizeImage(value: string | undefined) {
  if (!value) {
    return "";
  }
  if (value.startsWith("data:image")) {
    return value;
  }
  return `data:image/jpeg;base64,${value}`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asBoolean(value: unknown, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

function normalizeStatus(value: unknown): CameraSummary["status"] {
  if (value === "running" || value === true) {
    return "online";
  }
  if (value === "starting") {
    return "starting";
  }
  if (value === "error") {
    return "warning";
  }
  if (value === "offline") {
    return "offline";
  }
  return "idle";
}

function normalizeRuntimeMode(value: unknown): CameraSummary["runtime_mode"] {
  return value === "accurate" || value === "balanced" || value === "realtime"
    ? value
    : "balanced";
}

function normalizeConfidence(value: unknown) {
  const numeric = asNumber(value, 0);
  return numeric > 1 ? numeric / 100 : numeric;
}

function mapLoginResponse(payload: unknown): AuthSession {
  const item = asRecord(payload);
  const username = asString(item.username, "operator");
  const token = asString(item.access_token, asString(item.token));
  return {
    token,
    expires_at: asString(
      item.expires_at,
      new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString(),
    ),
    user: {
      id: username,
      name: username,
      role: asString(item.role, "Operator"),
      last_login_at: new Date().toISOString(),
    },
  };
}

function mapSystemStatus(payload: unknown): SystemStatus {
  const item = asRecord(payload);
  const appState = asRecord(item.app_state);
  const backendMode = asString(
    item.recognition_backend_mode,
    asString(item.backend_mode, "unknown"),
  );
  const provider = asString(
    item.recognition_provider,
    asString(item.provider_display, "unknown provider"),
  );
  const degraded =
    asBoolean(item.degraded) ||
    Boolean(asString(item.recognition_error)) ||
    backendMode === "unavailable";

  return {
    overall: degraded ? "degraded" : "healthy",
    uptime: "live backend",
    cpu_percent: asNumber(item.cpu_percent),
    gpu_percent: asNumber(item.gpu_percent),
    memory_percent: asNumber(item.memory_percent),
    temperature_c: asNumber(item.temperature_c),
    active_cameras: asNumber(item.active_cameras),
    total_cameras: asNumber(item.configured_cameras, asNumber(item.total_cameras)),
    total_faces: asNumber(item.total_users, asNumber(item.registered_users)),
    pending_model_update: asBoolean(item.model_pending),
    backend_mode: backendMode,
    provider,
    queue_backlog: asNumber(item.queue_backlog),
    last_sync_at: asString(item.time, new Date().toISOString()),
    inference: {
      avg_latency_ms: asNumber(item.avg_latency_ms),
      recognition_fps: asNumber(appState.recognition_fps),
      dropped_frames: asNumber(appState.dropped_frames),
      unknown_rate: asNumber(appState.unknown_rate),
    },
    services: [
      {
        name: "Backend API",
        state: degraded ? "degraded" : "healthy",
        message: degraded
          ? asString(item.recognition_error, "Backend reports degraded recognition state.")
          : "Task-01 backend API responded successfully.",
        latency_ms: 0,
        updated_at: asString(item.time, new Date().toISOString()),
      },
      {
        name: "Recognition Runtime",
        state:
          backendMode === "unavailable"
            ? "offline"
            : degraded
              ? "degraded"
              : "healthy",
        message: `${backendMode} / ${provider}`,
        latency_ms: 0,
        updated_at: asString(item.time, new Date().toISOString()),
      },
    ],
  };
}

function mapCamera(payload: unknown): CameraSummary {
  const item = asRecord(payload);
  const cameraId = asString(item.camera_id, "camera");
  const source = asString(item.source, asString(item.source_uri, "0"));
  const status = normalizeStatus(item.state ?? item.running);
  const location = asString(item.location, asString(item.name_location, "Unnamed location"));
  return {
    camera_id: cameraId,
    name: asString(item.display_name, location || `Camera ${cameraId}`),
    location,
    source,
    status,
    runtime_mode: normalizeRuntimeMode(item.runtime_mode),
    display_mode: "recognition",
    fps: asNumber(item.fps),
    latency_ms: asNumber(item.latency_ms),
    faces: asNumber(item.faces),
    alert_count: asNumber(item.alert_count),
    last_event_at: asString(
      item.last_frame_at,
      asString(item.started_at, new Date().toISOString()),
    ),
    resolution: asString(item.resolution, "live"),
    provider: asString(item.backend_mode, "Task-01 runtime"),
    preview_hint:
      asString(item.last_error) ||
      (status === "online" ? "Live stream connected." : "Waiting for camera start or first frame."),
  };
}

function mapActionResult(payload: unknown, fallbackMessage: string): ActionResult {
  const item = asRecord(payload);
  return {
    success: asBoolean(item.ok, asBoolean(item.stopped, true)),
    message: asString(item.message, fallbackMessage),
  };
}

function mapLog(payload: unknown, index: number): LogRecord {
  const item = asRecord(payload);
  const capturedAt = asString(
    item.captured_at,
    asString(item.timestamp, new Date().toISOString()),
  );
  return {
    id: `log-${capturedAt}-${index}`,
    person_name: asString(item.person_name, asString(item.name, "unknown")),
    location: asString(item.location, "Unknown location"),
    captured_at: capturedAt,
    emotion: asString(item.emotion, "unknown"),
    attendance_type: asString(item.attendance_type, "unclassified"),
    status: asString(item.status, "unrecorded"),
    similarity: normalizeConfidence(item.similarity),
    confidence: normalizeConfidence(item.confidence ?? item.similarity),
    camera_id: asString(item.camera_id),
  };
}

function mapAttendance(payload: unknown, index: number): AttendanceRecord {
  const item = asRecord(payload);
  const totals = asRecord(item.totals ?? item.counts);
  const status = Object.keys(totals)[0] ?? asString(item.status, "summary");
  const date = asString(item.date, new Date().toISOString().slice(0, 10));
  return {
    id: `attendance-${asString(item.name, "unknown")}-${index}`,
    name: asString(item.name, "unknown"),
    date,
    first_seen_at: asString(item.first_seen_at, `${date}T00:00:00+08:00`),
    last_seen_at: asString(item.last_seen_at, `${date}T23:59:59+08:00`),
    status,
    attendance_type: asString(item.attendance_type, "attendance summary"),
    location: asString(item.location, "multiple cameras"),
  };
}

function mapFace(payload: unknown): FaceProfile {
  const item = asRecord(payload);
  const name = asString(item.username, asString(item.name, "unknown"));
  const sampleCount = asNumber(item.sample_count);
  return {
    id: String(item.user_id ?? item.id ?? name),
    name,
    department: asString(item.department, "Ungrouped"),
    sample_count: sampleCount,
    quality: sampleCount >= 12 ? "excellent" : sampleCount >= 6 ? "good" : "warning",
    watchlist: asBoolean(item.watchlist),
    last_seen_at: asString(item.last_seen_at, new Date().toISOString()),
    tags: [asString(item.directory, "Task-01 face library")].filter(Boolean),
    avatar_seed: name,
  };
}

function mapEvent(payload: unknown): UiEvent {
  const envelope = asRecord(payload);
  const eventType = asString(envelope.event_type, asString(envelope.type, "status"));
  const body = asRecord(envelope.payload ?? payload);
  const occurredAt = asString(
    body.occurred_at,
    asString(envelope.emitted_at, asString(body.timestamp, new Date().toISOString())),
  );

  if (eventType === "alert.raised" || body.alert_id) {
    return {
      id: asString(body.alert_id, `alert-${occurredAt}`),
      camera_id: asString(body.camera_id),
      frame_id: asNumber(body.frame_id),
      timestamp: occurredAt,
      type: "alert",
      title: asString(body.title, "Alert event"),
      description: asString(body.message, "Backend pushed an alert."),
      severity:
        body.severity === "critical"
          ? "critical"
          : body.severity === "warning"
            ? "warning"
            : "info",
    };
  }

  return {
    id: asString(body.id, `${eventType}-${occurredAt}`),
    camera_id: asString(body.camera_id),
    frame_id: asNumber(body.frame_id),
    timestamp: occurredAt,
    type: eventType.includes("vision") ? "recognition" : "status",
    title: asString(body.title, eventType),
    description: asString(body.description, "Realtime backend event received."),
    severity: "info",
    person_name: asString(body.name) || undefined,
    emotion: asString(body.emotion) || undefined,
  };
}

export class LiveApi implements BackendApi {
  private token = "";

  setToken(token: string) {
    this.token = token;
  }

  private ensureBaseUrl() {
    if (!apiConfig.baseUrl) {
      throw new Error("VITE_API_BASE_URL is not configured for live mode.");
    }
    return apiConfig.baseUrl;
  }

  private ensureWsBaseUrl() {
    if (!apiConfig.wsBaseUrl) {
      throw new Error("VITE_WS_BASE_URL is not configured for live WebSocket mode.");
    }
    return apiConfig.wsBaseUrl;
  }

  private async request<T>(
    path: string,
    init: RequestInit = {},
    withAuth = true,
  ): Promise<T> {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(
      () => controller.abort(),
      apiConfig.timeoutMs,
    );

    try {
      const response = await fetch(`${this.ensureBaseUrl()}${path}`, {
        ...init,
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          ...(withAuth && this.token
            ? { Authorization: `Bearer ${this.token}` }
            : {}),
          ...init.headers,
        },
      });

      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }

      return (await response.json()) as T;
    } finally {
      globalThis.clearTimeout(timeout);
    }
  }

  private connectSocket<T>(
    path: string,
    mapMessage: (payload: unknown) => T,
    onMessage: (value: T) => void,
    onError?: (error: Error) => void,
  ) {
    const rawUrl = `${this.ensureWsBaseUrl()}${path}`;
    const separator = rawUrl.includes("?") ? "&" : "?";
    const url = this.token
      ? `${rawUrl}${separator}token=${encodeURIComponent(this.token)}`
      : rawUrl;
    const socket = new WebSocket(url);

    socket.onmessage = (event) => {
      try {
        const raw = JSON.parse(String(event.data));
        onMessage(mapMessage(raw));
      } catch (error) {
        onError?.(
          error instanceof Error ? error : new Error("Unable to parse WebSocket message."),
        );
      }
    };

    socket.onerror = () => {
      onError?.(new Error(`WebSocket connection failed: ${rawUrl}`));
    };

    return () => {
      if (
        socket.readyState === WebSocket.OPEN ||
        socket.readyState === WebSocket.CONNECTING
      ) {
        socket.close();
      }
    };
  }

  login(credentials: AuthCredentials) {
    return this.request<unknown>(
      "/api/auth/login",
      {
        method: "POST",
        body: JSON.stringify(credentials),
      },
      false,
    ).then(mapLoginResponse);
  }

  getSystemStatus() {
    return this.request<unknown>("/api/system/status").then(mapSystemStatus);
  }

  getCameras() {
    return this.request<unknown>("/api/cameras").then((payload) => {
      const item = asRecord(payload);
      const list = Array.isArray(payload)
        ? payload
        : Array.isArray(item.items)
          ? item.items
          : [];
      return list.map(mapCamera);
    });
  }

  startCamera(cameraId: string) {
    return this.request<unknown>("/api/cameras/start", {
      method: "POST",
      body: JSON.stringify({ camera_id: cameraId }),
    }).then((payload) => mapActionResult(payload, "Camera start request sent."));
  }

  stopCamera(cameraId: string) {
    return this.request<unknown>("/api/cameras/stop", {
      method: "POST",
      body: JSON.stringify({ camera_id: cameraId }),
    }).then((payload) => mapActionResult(payload, "Camera stop request sent."));
  }

  getLogs(filters: LogFilters) {
    return this.request<unknown>(
      buildQuery("/api/logs", {
        name: filters.name,
        location: filters.location,
        status: filters.status,
        attendance_type: filters.attendance_type,
        search: filters.search,
        start_time: filters.start_time,
        end_time: filters.end_time,
        page: 1,
        page_size: 50,
      }),
    ).then((payload) => {
      const item = asRecord(payload);
      const list = Array.isArray(payload)
        ? payload
        : Array.isArray(item.items)
          ? item.items
          : [];
      return list.map(mapLog);
    });
  }

  getAttendance(filters: AttendanceFilters) {
    return this.request<unknown>(
      buildQuery("/api/attendance", {
        search: filters.search,
        status: filters.status,
        start_time: filters.start_time,
        end_time: filters.end_time,
      }),
    ).then((payload) => {
      const item = asRecord(payload);
      const list = Array.isArray(payload)
        ? payload
        : Array.isArray(item.items)
          ? item.items
          : Array.isArray(item.summary)
            ? item.summary
            : [];
      return list.map(mapAttendance);
    });
  }

  getFaceLibrary(): Promise<FaceProfile[]> {
    return this.request<unknown>("/api/faces").then((payload) => {
      const item = asRecord(payload);
      const list = Array.isArray(payload)
        ? payload
        : Array.isArray(item.items)
          ? item.items
          : [];
      return list.map(mapFace);
    });
  }

  registerFace(payload: FaceRegistrationPayload): Promise<ActionResult> {
    const placeholderJpeg =
      "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Al//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2gAMAwEAAgADAAAAEP/EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EABQQAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEAAT8QH//Z";
    return this.request<unknown>("/api/faces/register", {
      method: "POST",
      body: JSON.stringify({
        username: payload.name,
        images: [{ filename: "task-02-placeholder.jpg", content_base64: placeholderJpeg }],
        replace_existing: false,
        rebuild_model: false,
      }),
    }).then((response) => mapActionResult(response, "Face registration request sent."));
  }

  deleteFace(name: string) {
    return this.request<unknown>(`/api/faces/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }).then((payload) => mapActionResult(payload, "Face delete request sent."));
  }

  connectEvents(
    onMessage: (event: UiEvent) => void,
    onError?: (error: Error) => void,
  ) {
    return this.connectSocket<UiEvent>("/ws/events", mapEvent, onMessage, onError);
  }

  connectStream(
    cameraId: string,
    onMessage: (frame: StreamFrame) => void,
    onError?: (error: Error) => void,
  ) {
    return this.connectSocket<StreamFrame>(
      `/ws/stream/${encodeURIComponent(cameraId)}`,
      (payload) => {
        const raw = asRecord(payload);
        return {
          camera_id: asString(raw.camera_id, cameraId),
          frame_id: asNumber(raw.frame_id),
          timestamp: asString(
            raw.timestamp,
            asString(raw.captured_at, new Date().toISOString()),
          ),
          image: normalizeImage(
            asString(raw.image, asString(raw.image_base64, asString(raw.image_data))),
          ),
        };
      },
      onMessage,
      onError,
    );
  }
}
