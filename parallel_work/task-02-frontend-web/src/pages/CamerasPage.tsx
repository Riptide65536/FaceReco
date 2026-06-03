import { useMemo, useState } from "react";

import { useShellContext } from "../app/useShellContext";
import { Panel } from "../components/Panel";
import { StateBlock } from "../components/StateBlock";
import { StatusBadge } from "../components/StatusBadge";
import { VideoTile } from "../components/VideoTile";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { api } from "../lib/api/client";
import { formatLatency, formatRelativeTime } from "../lib/format";

export function CamerasPage() {
  const { refreshSystemStatus } = useShellContext();
  const camerasResource = useAsyncResource(() => api.getCameras(), [], {
    pollMs: 12_000,
  });
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const [busyId, setBusyId] = useState<string | undefined>();
  const [feedback, setFeedback] = useState<string | undefined>();

  const cameras = useMemo(() => camerasResource.data ?? [], [camerasResource.data]);

  const filtered = useMemo(
    () =>
      cameras.filter((camera) =>
        [camera.name, camera.location, camera.source]
          .join(" ")
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [cameras, query],
  );

  const effectiveSelectedId = selectedId ?? filtered[0]?.camera_id;
  const selectedCamera =
    filtered.find((camera) => camera.camera_id === effectiveSelectedId) ??
    filtered[0];

  return (
    <div className="page-grid">
      <Panel
        eyebrow="Fleet Controls"
        title="摄像头管理"
        subtitle="按状态查看视频源运行情况，并为每一路保留启停入口与关键性能数据。"
        actions={
          <div className="toolbar-inline">
            <input
              className="toolbar-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索名称、位置或流地址"
            />
            <button
              className="ghost-button"
              onClick={() => {
                void camerasResource.refresh();
              }}
            >
              刷新列表
            </button>
          </div>
        }
      >
        {feedback ? <p className="inline-feedback">{feedback}</p> : null}
        {camerasResource.loading && !filtered.length ? (
          <StateBlock
            title="正在读取摄像头列表"
            description="等待 GET /api/cameras 返回视频源基础信息。"
          />
        ) : (
          <div className="camera-layout">
            <div className="camera-list">
              {filtered.map((camera) => (
                <button
                  key={camera.camera_id}
                  className={
                    selectedCamera?.camera_id === camera.camera_id
                      ? "camera-item camera-item--active"
                      : "camera-item"
                  }
                  onClick={() => setSelectedId(camera.camera_id)}
                >
                  <div className="camera-item__head">
                    <div>
                      <strong>{camera.name}</strong>
                      <p>{camera.location}</p>
                    </div>
                    <StatusBadge
                      label={camera.status}
                      tone={
                        camera.status === "online"
                          ? "online"
                          : camera.status === "warning"
                            ? "warning"
                            : camera.status === "idle"
                              ? "idle"
                              : "offline"
                      }
                      compact
                    />
                  </div>
                  <div className="camera-item__stats">
                    <span>{camera.runtime_mode}</span>
                    <span>{formatLatency(camera.latency_ms)}</span>
                    <span>{camera.fps.toFixed(1)} FPS</span>
                  </div>
                </button>
              ))}
            </div>

            <div className="camera-detail">
              {selectedCamera ? (
                <>
                  <VideoTile camera={selectedCamera} compact />
                  <div className="camera-detail__facts">
                    <div className="fact-card">
                      <span>流地址</span>
                      <strong>{selectedCamera.source}</strong>
                    </div>
                    <div className="fact-card">
                      <span>最后事件</span>
                      <strong>{formatRelativeTime(selectedCamera.last_event_at)}</strong>
                    </div>
                    <div className="fact-card">
                      <span>Provider</span>
                      <strong>{selectedCamera.provider}</strong>
                    </div>
                    <div className="fact-card">
                      <span>识别人脸数</span>
                      <strong>{selectedCamera.faces}</strong>
                    </div>
                  </div>
                  <div className="camera-detail__actions">
                    <button
                      className="primary-button"
                      disabled={busyId === selectedCamera.camera_id}
                      onClick={() => {
                        setBusyId(selectedCamera.camera_id);
                        setFeedback(undefined);
                        void api
                          .startCamera(selectedCamera.camera_id)
                          .then((result) => {
                            setFeedback(result.message);
                          })
                          .finally(() => {
                            setBusyId(undefined);
                            void Promise.all([
                              camerasResource.refresh(),
                              refreshSystemStatus(),
                            ]);
                          });
                      }}
                    >
                      启动
                    </button>
                    <button
                      className="ghost-button"
                      disabled={busyId === selectedCamera.camera_id}
                      onClick={() => {
                        setBusyId(selectedCamera.camera_id);
                        setFeedback(undefined);
                        void api
                          .stopCamera(selectedCamera.camera_id)
                          .then((result) => {
                            setFeedback(result.message);
                          })
                          .finally(() => {
                            setBusyId(undefined);
                            void Promise.all([
                              camerasResource.refresh(),
                              refreshSystemStatus(),
                            ]);
                          });
                      }}
                    >
                      停止
                    </button>
                  </div>
                </>
              ) : (
                <StateBlock
                  title="没有匹配的视频源"
                  description="请调整搜索关键词，或等待后端返回更多摄像头数据。"
                />
              )}
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}
