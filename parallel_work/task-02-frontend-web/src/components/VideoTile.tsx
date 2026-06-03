import { useStreamPreview } from "../hooks/useRealtimeFeed";
import { cn, formatLatency, formatRelativeTime } from "../lib/format";
import type { CameraSummary } from "../lib/api/types";
import { StatusBadge } from "./StatusBadge";

interface VideoTileProps {
  camera: CameraSummary;
  compact?: boolean;
}

function toneFromStatus(status: CameraSummary["status"]) {
  switch (status) {
    case "online":
      return "online";
    case "warning":
      return "warning";
    case "idle":
      return "idle";
    case "starting":
      return "starting";
    default:
      return "offline";
  }
}

function labelFromStatus(status: CameraSummary["status"]) {
  switch (status) {
    case "online":
      return "在线";
    case "warning":
      return "告警";
    case "idle":
      return "空闲";
    case "starting":
      return "启动中";
    default:
      return "离线";
  }
}

export function VideoTile({ camera, compact = false }: VideoTileProps) {
  const { frame } = useStreamPreview(camera.camera_id, camera.status !== "offline");

  return (
    <article className={cn("video-tile", compact && "video-tile--compact")}>
      <div className="video-tile__media">
        {frame?.image ? (
          <img
            className="video-tile__image"
            src={frame.image}
            alt={`${camera.name} stream preview`}
          />
        ) : (
          <div className="video-tile__placeholder">
            <span>等待视频流</span>
          </div>
        )}
        <div className="video-tile__overlay">
          <div className="video-tile__overlay-top">
            <StatusBadge
              label={labelFromStatus(camera.status)}
              tone={toneFromStatus(camera.status)}
              compact
            />
            <span className="video-chip">{camera.runtime_mode}</span>
          </div>
          <div className="video-tile__overlay-bottom">
            <div>
              <p className="video-tile__camera">{camera.name}</p>
              <p className="video-tile__hint">{camera.preview_hint}</p>
            </div>
            <div className="video-tile__stats">
              <span>{camera.fps.toFixed(1)} FPS</span>
              <span>{formatLatency(camera.latency_ms)}</span>
            </div>
          </div>
        </div>
      </div>
      <div className="video-tile__meta">
        <div>
          <p className="video-tile__location">{camera.location}</p>
          <p className="video-tile__subtle">
            最后事件 {formatRelativeTime(camera.last_event_at)}
          </p>
        </div>
        <div className="video-tile__facts">
          <span>{camera.faces} faces</span>
          <span>{camera.resolution}</span>
        </div>
      </div>
    </article>
  );
}
