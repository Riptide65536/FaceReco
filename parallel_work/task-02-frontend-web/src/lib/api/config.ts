import type { ApiMode } from "./types";

function normalizeBaseUrl(value: string | undefined) {
  return (value ?? "").replace(/\/+$/, "");
}

function inferWsBaseUrl(baseUrl: string) {
  if (!baseUrl) {
    return "";
  }
  if (baseUrl.startsWith("https://")) {
    return `wss://${baseUrl.slice("https://".length)}`;
  }
  if (baseUrl.startsWith("http://")) {
    return `ws://${baseUrl.slice("http://".length)}`;
  }
  return baseUrl;
}

const rawMode = (import.meta.env.VITE_API_MODE ?? "auto") as ApiMode;
const baseUrl = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL);

export const apiConfig = {
  mode: rawMode,
  baseUrl,
  wsBaseUrl: normalizeBaseUrl(
    import.meta.env.VITE_WS_BASE_URL ?? inferWsBaseUrl(baseUrl),
  ),
  timeoutMs: Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 4500),
};
