import type { CameraSummary, Severity } from "./types";

function hashSeed(input: string) {
  return Array.from(input).reduce(
    (total, char, index) => total + char.charCodeAt(0) * (index + 3),
    0,
  );
}

function escapeXml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function severityColor(severity: Severity) {
  switch (severity) {
    case "critical":
      return "#ff6b57";
    case "warning":
      return "#ffb347";
    case "success":
      return "#1fd3a7";
    default:
      return "#78d7ff";
  }
}

export function createMockFrame(
  camera: CameraSummary,
  frameId: number,
  statusText: string,
  severity: Severity,
) {
  const seed = hashSeed(camera.camera_id);
  const hueA = 186 + (seed % 26);
  const hueB = 28 + (seed % 18);
  const boxX = 90 + ((frameId * 17 + seed) % 220);
  const boxY = 110 + ((frameId * 13 + seed) % 60);
  const secondaryX = 330 + ((frameId * 11 + seed) % 70);
  const secondaryY = 120 + ((frameId * 9 + seed) % 40);
  const nowText = new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const accent = severityColor(severity);
  const svg = `
    <svg width="640" height="360" viewBox="0 0 640 360" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bg" x1="36" y1="22" x2="595" y2="340" gradientUnits="userSpaceOnUse">
          <stop stop-color="hsl(${hueA}, 68%, 19%)" />
          <stop offset="0.56" stop-color="#0b1521" />
          <stop offset="1" stop-color="hsl(${hueB}, 72%, 22%)" />
        </linearGradient>
        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M20 0H0V20" fill="none" stroke="rgba(255,255,255,0.06)" />
        </pattern>
      </defs>
      <rect width="640" height="360" rx="28" fill="url(#bg)" />
      <rect width="640" height="360" rx="28" fill="url(#grid)" />
      <ellipse cx="184" cy="298" rx="122" ry="34" fill="rgba(0,0,0,0.28)" />
      <ellipse cx="470" cy="302" rx="98" ry="30" fill="rgba(0,0,0,0.22)" />
      <path d="M104 310C126 238 154 172 186 118C208 80 244 74 278 102C306 124 324 182 330 260L104 310Z" fill="rgba(255,255,255,0.08)" />
      <path d="M388 310C402 222 418 154 446 116C470 84 504 80 534 112C560 142 574 204 578 310H388Z" fill="rgba(255,255,255,0.06)" />
      <rect x="${boxX}" y="${boxY}" width="104" height="134" rx="12" stroke="${accent}" stroke-width="4"/>
      <rect x="${secondaryX}" y="${secondaryY}" width="72" height="94" rx="10" stroke="rgba(120,215,255,0.72)" stroke-width="3"/>
      <rect x="28" y="24" width="182" height="38" rx="18" fill="rgba(7,14,22,0.68)" />
      <text x="48" y="48" fill="#F7FBFF" font-size="16" font-family="Bahnschrift, 'Microsoft YaHei UI', sans-serif">${escapeXml(camera.name)}</text>
      <text x="30" y="330" fill="#BFD1E0" font-size="14" font-family="Bahnschrift, 'Microsoft YaHei UI', sans-serif">${escapeXml(camera.location)}</text>
      <rect x="454" y="24" width="158" height="36" rx="18" fill="rgba(7,14,22,0.68)" />
      <text x="480" y="47" fill="#FAF5E8" font-size="14" font-family="Bahnschrift, 'Microsoft YaHei UI', sans-serif">${escapeXml(statusText)}</text>
      <text x="448" y="330" fill="#E6EEF5" font-size="14" font-family="Consolas, monospace">${nowText}</text>
      <rect x="40" y="278" width="142" height="32" rx="16" fill="rgba(0,0,0,0.38)" />
      <text x="62" y="300" fill="${accent}" font-size="14" font-family="Bahnschrift, 'Microsoft YaHei UI', sans-serif">Face Track ${String(frameId).padStart(4, "0")}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}
