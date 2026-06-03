import { Panel } from "../components/Panel";
import { MetricCard } from "../components/MetricCard";
import { StateBlock } from "../components/StateBlock";
import { StatusBadge } from "../components/StatusBadge";
import { VideoTile } from "../components/VideoTile";
import { useShellContext } from "../app/useShellContext";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { useEventFeed } from "../hooks/useRealtimeFeed";
import { api } from "../lib/api/client";
import {
  formatDateTime,
  formatLatency,
  formatPercent,
  formatRelativeTime,
} from "../lib/format";

function severityTone(severity: string) {
  switch (severity) {
    case "success":
      return "success";
    case "warning":
      return "warning";
    case "critical":
      return "critical";
    default:
      return "info";
  }
}

export function OverviewPage() {
  const { systemStatus, refreshSystemStatus } = useShellContext();
  const camerasResource = useAsyncResource(() => api.getCameras(), [], {
    pollMs: 10_000,
  });
  const logsResource = useAsyncResource(() => api.getLogs({}), [], {
    pollMs: 16_000,
  });
  const { events } = useEventFeed(7);

  const cameras = camerasResource.data ?? [];
  const logs = (logsResource.data ?? []).slice(0, 5);

  return (
    <div className="page-grid">
      <div className="metric-grid">
        <MetricCard
          label="在线摄像头"
          value={`${systemStatus?.active_cameras ?? 0}/${systemStatus?.total_cameras ?? 0}`}
          helper="保持实时预览优先"
          tone="accent"
        />
        <MetricCard
          label="识别延迟"
          value={formatLatency(systemStatus?.inference.avg_latency_ms ?? 0)}
          helper="综合摄像头与推理队列"
        />
        <MetricCard
          label="未知率"
          value={formatPercent((systemStatus?.inference.unknown_rate ?? 0) * 100)}
          helper="需要持续压低的关键指标"
          tone="warning"
        />
        <MetricCard
          label="模型队列"
          value={`${systemStatus?.queue_backlog ?? 0}`}
          helper="待处理识别任务数量"
        />
      </div>

      <div className="content-grid content-grid--overview">
        <Panel
          className="panel--featured"
          eyebrow="Live Matrix"
          title="实时监控矩阵"
          subtitle="视频流区域保持视觉优先，识别信息以悬浮信息层叠加。"
          actions={
            <button
              className="ghost-button"
              onClick={() => {
                void Promise.all([
                  camerasResource.refresh(),
                  logsResource.refresh(),
                  refreshSystemStatus(),
                ]);
              }}
            >
              刷新总览
            </button>
          }
        >
          {camerasResource.loading && !cameras.length ? (
            <StateBlock
              title="正在加载视频矩阵"
              description="正在获取摄像头清单与首批预览帧。"
            />
          ) : cameras.length ? (
            <div className="video-grid">
              {cameras.slice(0, 4).map((camera) => (
                <VideoTile key={camera.camera_id} camera={camera} />
              ))}
            </div>
          ) : (
            <StateBlock
              title="暂无摄像头"
              description="当前没有可展示的视频源，请前往摄像头管理页接入。"
            />
          )}
        </Panel>

        <Panel
          eyebrow="Event Stream"
          title="告警与识别动态"
          subtitle="把陌生人告警、重点对象命中和状态变更聚合到同一个时间线。"
        >
          <div className="event-list">
            {events.length ? (
              events.map((event) => (
                <article key={event.id} className="event-item">
                  <div className="event-item__head">
                    <StatusBadge
                      label={event.severity}
                      tone={severityTone(event.severity)}
                      compact
                    />
                    <span className="event-item__time">
                      {formatRelativeTime(event.timestamp)}
                    </span>
                  </div>
                  <h3>{event.title}</h3>
                  <p>{event.description}</p>
                </article>
              ))
            ) : (
              <StateBlock
                title="等待事件流"
                description="WS /ws/events 尚未有消息时，会在这里显示最新识别事件。"
              />
            )}
          </div>
        </Panel>

        <Panel
          eyebrow="Recognition Feed"
          title="最新识别记录"
          subtitle="保留最近识别结果，方便值班人员快速确认当前现场。"
        >
          <div className="timeline-list">
            {logs.length ? (
              logs.map((log) => (
                <article key={log.id} className="timeline-item">
                  <div>
                    <p className="timeline-item__title">{log.person_name}</p>
                    <p className="timeline-item__meta">
                      {log.location} · {log.attendance_type}
                    </p>
                  </div>
                  <div className="timeline-item__tail">
                    <strong>{Math.round(log.confidence * 100)}%</strong>
                    <span>{formatDateTime(log.captured_at)}</span>
                  </div>
                </article>
              ))
            ) : (
              <StateBlock
                title="暂无识别日志"
                description="日志接口返回为空时，这里会展示空状态而不是空白区域。"
              />
            )}
          </div>
        </Panel>

        <Panel
          eyebrow="System Snapshot"
          title="当前运行快照"
          subtitle="服务健康、资源占用和待办风险一眼可见。"
        >
          {systemStatus ? (
            <div className="snapshot-grid">
              <div className="snapshot-row">
                <span>CPU</span>
                <strong>{formatPercent(systemStatus.cpu_percent)}</strong>
              </div>
              <div className="snapshot-row">
                <span>GPU</span>
                <strong>{formatPercent(systemStatus.gpu_percent)}</strong>
              </div>
              <div className="snapshot-row">
                <span>内存</span>
                <strong>{formatPercent(systemStatus.memory_percent)}</strong>
              </div>
              <div className="snapshot-row">
                <span>模型更新</span>
                <strong>
                  {systemStatus.pending_model_update ? "存在待更新样本" : "样本库同步正常"}
                </strong>
              </div>
              <div className="snapshot-row">
                <span>Provider</span>
                <strong>{systemStatus.provider}</strong>
              </div>
            </div>
          ) : (
            <StateBlock
              title="系统状态暂未返回"
              description="GET /api/system/status 可用后，这里会展示完整运行指标。"
            />
          )}
        </Panel>
      </div>
    </div>
  );
}
