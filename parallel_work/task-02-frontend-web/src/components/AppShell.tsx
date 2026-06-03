import { NavLink, Outlet, useLocation } from "react-router-dom";

import { findRouteMeta, navRoutes } from "../app/routeMeta";
import { useSession } from "../app/session";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { api, apiConfig } from "../lib/api/client";
import { formatRelativeTime } from "../lib/format";
import { StatusBadge } from "./StatusBadge";

function mapHealthTone(overall?: string) {
  switch (overall) {
    case "healthy":
      return "healthy";
    case "degraded":
      return "degraded";
    default:
      return "offline";
  }
}

function mapHealthLabel(overall?: string) {
  switch (overall) {
    case "healthy":
      return "系统稳定";
    case "degraded":
      return "需要关注";
    default:
      return "状态未知";
  }
}

export function AppShell() {
  const location = useLocation();
  const routeMeta = findRouteMeta(location.pathname);
  const { logout, session } = useSession();
  const statusResource = useAsyncResource(() => api.getSystemStatus(), [], {
    pollMs: 15_000,
  });

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand-card">
          <p className="brand-card__eyebrow">Face Ops Hub</p>
          <h1 className="brand-card__title">多摄像头识别控制台</h1>
          <p className="brand-card__copy">
            将旧版 PySide2 工具升级为更清晰的产品化监控操作台。
          </p>
        </div>

        <nav className="sidebar__nav">
          {navRoutes.map((route) => (
            <NavLink
              key={route.path}
              to={route.path}
              className={({ isActive }) =>
                isActive ? "nav-link nav-link--active" : "nav-link"
              }
            >
              <span className="nav-link__eyebrow">{route.eyebrow}</span>
              <span className="nav-link__label">{route.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__footer">
          <p className="sidebar__footer-label">当前模式</p>
          <div className="sidebar__chips">
            <span className="sidebar-chip">{apiConfig.mode}</span>
            <span className="sidebar-chip">
              {statusResource.data?.provider ?? "provider pending"}
            </span>
          </div>
        </div>
      </aside>

      <div className="shell__main">
        <header className="topbar">
          <div>
            <p className="topbar__eyebrow">{routeMeta.eyebrow}</p>
            <h2 className="topbar__title">{routeMeta.label}</h2>
            <p className="topbar__description">{routeMeta.description}</p>
          </div>

          <div className="topbar__actions">
            <div className="topbar__status">
              <StatusBadge
                label={mapHealthLabel(statusResource.data?.overall)}
                tone={mapHealthTone(statusResource.data?.overall)}
              />
              <span className="topbar__muted">
                {statusResource.data
                  ? `同步于 ${formatRelativeTime(statusResource.data.last_sync_at)}`
                  : "等待状态同步"}
              </span>
            </div>
            <div className="operator-chip">
              <strong>{session?.user.name}</strong>
              <span>{session?.user.role}</span>
            </div>
            <button className="ghost-button" onClick={logout}>
              退出
            </button>
          </div>
        </header>

        <main className="shell__content">
          <Outlet
            context={{
              apiMode: apiConfig.mode,
              statusLoading: statusResource.loading,
              statusRefreshing: statusResource.refreshing,
              systemStatus: statusResource.data,
              refreshSystemStatus: statusResource.refresh,
            }}
          />
        </main>
      </div>
    </div>
  );
}
