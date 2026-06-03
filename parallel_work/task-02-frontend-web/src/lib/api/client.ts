import { apiConfig } from "./config";
import { LiveApi } from "./liveApi";
import { mockApi } from "./mockApi";
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

const SESSION_STORAGE_KEY = "task02.frontend.session";
const liveApi = new LiveApi();

function shouldUseMockOnly() {
  return apiConfig.mode === "mock" || (apiConfig.mode === "auto" && !apiConfig.baseUrl);
}

function shouldUseLiveOnly() {
  return apiConfig.mode === "live";
}

async function executeWithFallback<T>(
  liveAction: () => Promise<T>,
  mockAction: () => Promise<T>,
) {
  if (shouldUseMockOnly()) {
    return mockAction();
  }
  if (shouldUseLiveOnly()) {
    return liveAction();
  }
  try {
    return await liveAction();
  } catch (error) {
    console.warn("[task-02] live call failed, fallback to mock:", error);
    return mockAction();
  }
}

function connectWithFallback<T>(
  liveConnect: (
    onMessage: (value: T) => void,
    onError?: (error: Error) => void,
  ) => () => void,
  mockConnect: (
    onMessage: (value: T) => void,
    onError?: (error: Error) => void,
  ) => () => void,
  onMessage: (value: T) => void,
  onError?: (error: Error) => void,
) {
  if (shouldUseMockOnly()) {
    return mockConnect(onMessage, onError);
  }
  if (shouldUseLiveOnly()) {
    return liveConnect(onMessage, onError);
  }

  let liveUnsubscribe = () => {};
  let mockUnsubscribe = () => {};
  let switched = false;

  const switchToMock = (error: Error) => {
    onError?.(error);
    if (switched) {
      return;
    }
    switched = true;
    liveUnsubscribe();
    mockUnsubscribe = mockConnect(onMessage, onError);
  };

  try {
    liveUnsubscribe = liveConnect(onMessage, switchToMock);
  } catch (error) {
    switchToMock(
      error instanceof Error ? error : new Error("Unable to create live stream"),
    );
  }

  return () => {
    liveUnsubscribe();
    mockUnsubscribe();
  };
}

export function setApiToken(token: string) {
  liveApi.setToken(token);
}

export function syncApiTokenFromStorage() {
  if (typeof window === "undefined") {
    return;
  }
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw) as { token?: string };
    setApiToken(parsed.token ?? "");
  } catch {
    setApiToken("");
  }
}

export const api: BackendApi = {
  login(credentials: AuthCredentials) {
    return executeWithFallback<AuthSession>(
      () => liveApi.login(credentials),
      () => mockApi.login(credentials),
    );
  },

  getSystemStatus() {
    return executeWithFallback<SystemStatus>(
      () => liveApi.getSystemStatus(),
      () => mockApi.getSystemStatus(),
    );
  },

  getCameras() {
    return executeWithFallback<CameraSummary[]>(
      () => liveApi.getCameras(),
      () => mockApi.getCameras(),
    );
  },

  startCamera(cameraId: string) {
    return executeWithFallback<ActionResult>(
      () => liveApi.startCamera(cameraId),
      () => mockApi.startCamera(cameraId),
    );
  },

  stopCamera(cameraId: string) {
    return executeWithFallback<ActionResult>(
      () => liveApi.stopCamera(cameraId),
      () => mockApi.stopCamera(cameraId),
    );
  },

  getLogs(filters: LogFilters) {
    return executeWithFallback<LogRecord[]>(
      () => liveApi.getLogs(filters),
      () => mockApi.getLogs(filters),
    );
  },

  getAttendance(filters: AttendanceFilters) {
    return executeWithFallback<AttendanceRecord[]>(
      () => liveApi.getAttendance(filters),
      () => mockApi.getAttendance(filters),
    );
  },

  getFaceLibrary() {
    return executeWithFallback<FaceProfile[]>(
      () => liveApi.getFaceLibrary(),
      () => mockApi.getFaceLibrary(),
    );
  },

  registerFace(payload: FaceRegistrationPayload) {
    return executeWithFallback<ActionResult>(
      () => liveApi.registerFace(payload),
      () => mockApi.registerFace(payload),
    );
  },

  deleteFace(name: string) {
    return executeWithFallback<ActionResult>(
      () => liveApi.deleteFace(name),
      () => mockApi.deleteFace(name),
    );
  },

  connectEvents(
    onMessage: (event: UiEvent) => void,
    onError?: (error: Error) => void,
  ) {
    return connectWithFallback<UiEvent>(
      (nextMessage, nextError) => liveApi.connectEvents(nextMessage, nextError),
      (nextMessage, nextError) => mockApi.connectEvents(nextMessage, nextError),
      onMessage,
      onError,
    );
  },

  connectStream(
    cameraId: string,
    onMessage: (frame: StreamFrame) => void,
    onError?: (error: Error) => void,
  ) {
    return connectWithFallback<StreamFrame>(
      (nextMessage, nextError) =>
        liveApi.connectStream(cameraId, nextMessage, nextError),
      (nextMessage, nextError) =>
        mockApi.connectStream(cameraId, nextMessage, nextError),
      onMessage,
      onError,
    );
  },
};

export { apiConfig };
