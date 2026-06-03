import { useMemo } from "react";

import { useShellContext } from "../app/useShellContext";
import { Panel } from "../components/Panel";
import { StateBlock } from "../components/StateBlock";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { api } from "../lib/api/client";
import { contractSupportItems, pendingIntegrationGaps } from "../lib/integration";
import { formatDateTime, formatPercent } from "../lib/format";

function supportTone(support: string) {
  switch (support) {
    case "ready":
      return "success";
    case "mock-only":
      return "warning";
    default:
      return "info";
  }
}

export function SystemPage() {
  const { apiMode, systemStatus, refreshSystemStatus } = useShellContext();
  const camerasResource = useAsyncResource(() => api.getCameras(), [], {
    pollMs: 16_000,
  });

  const cameraSummary = useMemo(() => {
    const cameras = camerasResource.data ?? [];
    return cameras.map((camera) => ({
      name: camera.name,
      status: camera.status,
      runtime: camera.runtime_mode,
    }));
  }, [camerasResource.data]);

  return (
    <div className="page-grid">
      <Panel
        eyebrow="Ops Health"
        title="系统状态"
        subtitle="围绕服务健康、资源占用和接口联通情况给出运维视图。"
        actions={
          <button
            className="ghost-button"
            onClick={() => {
              void Promise.all([refreshSystemStatus(), camerasResource.refresh()]);
            }}
          >
            立即同步
          </button>
        }
      >
        {systemStatus ? (
          <div className="ops-grid">
            <div className="ops-card">
              <h3>资源占用</h3>
              <div className="ops-row">
                <span>CPU</span>
                <strong>{formatPercent(systemStatus.cpu_percent)}</strong>
              </div>
              <div className="ops-row">
                <span>GPU</span>
                <strong>{formatPercent(systemStatus.gpu_percent)}</strong>
              </div>
              <div className="ops-row">
                <span>内存</span>
                <strong>{formatPercent(systemStatus.memory_percent)}</strong>
              </div>
              <div className="ops-row">
                <span>温度</span>
                <strong>{systemStatus.temperature_c.toFixed(1)} C</strong>
              </div>
            </div>

            <div className="ops-card">
              <h3>服务健康</h3>
              {systemStatus.services.map((service) => (
                <div key={service.name} className="service-row">
                  <div>
                    <strong>{service.name}</strong>
                    <p>{service.message}</p>
                  </div>
                  <StatusBadge
                    label={service.state}
                    tone={
                      service.state === "healthy"
                        ? "healthy"
                        : service.state === "degraded"
                          ? "degraded"
                          : "offline"
                    }
                    compact
                  />
                </div>
              ))}
            </div>

            <div className="ops-card">
              <h3>摄像头运行面</h3>
              {cameraSummary.length ? (
                cameraSummary.map((camera) => (
                  <div key={camera.name} className="service-row">
                    <div>
                      <strong>{camera.name}</strong>
                      <p>{camera.runtime}</p>
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
                ))
              ) : (
                <StateBlock
                  title="摄像头摘要待加载"
                  description="等待获取摄像头列表后展示各路运行状态。"
                />
              )}
            </div>
          </div>
        ) : (
          <StateBlock
            title="系统状态不可用"
            description="请先联通 GET /api/system/status 或使用 mock 模式。"
          />
        )}
      </Panel>

      <Panel
        eyebrow="Contract Matrix"
        title="前后端接口支持矩阵"
        subtitle={`当前页面运行在 ${apiMode} 模式，下面列出已接、mock 回退和待冻结的接口。`}
      >
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>能力</th>
                <th>方法</th>
                <th>路径</th>
                <th>状态</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {contractSupportItems.map((item) => (
                <tr key={`${item.method}-${item.path}`}>
                  <td>{item.label}</td>
                  <td>{item.method}</td>
                  <td>{item.path}</td>
                  <td>
                    <StatusBadge
                      label={item.support}
                      tone={supportTone(item.support)}
                      compact
                    />
                  </td>
                  <td>{item.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel
        eyebrow="Pending Gaps"
        title="尚未联通的接口与风险"
        subtitle={`最后状态同步时间：${
          systemStatus ? formatDateTime(systemStatus.last_sync_at) : "未同步"
        }`}
      >
        <ul className="risk-list">
          {pendingIntegrationGaps.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
