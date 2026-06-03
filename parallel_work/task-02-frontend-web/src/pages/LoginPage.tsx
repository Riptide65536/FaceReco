import { startTransition, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { useSession } from "../app/session";
import { apiConfig } from "../lib/api/client";

export function LoginPage() {
  const navigate = useNavigate();
  const { isAuthenticated, login } = useSession();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("FaceReco2026!");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>();

  if (isAuthenticated) {
    return <Navigate to="/overview" replace />;
  }

  return (
    <div className="login-page">
      <section className="login-hero">
        <div className="login-hero__frame">
          <p className="login-hero__eyebrow">Surveillance Product Refresh</p>
          <h1 className="login-hero__title">
            把桌面式监控工具
            <br />
            升级成真正可交付的产品界面
          </h1>
          <p className="login-hero__copy">
            这个前端围绕多路视频、识别结果、告警等级和系统状态重新组织信息层级，
            不再沿用旧版 PySide2 的临时工具感。
          </p>

          <div className="hero-metrics">
            <article className="hero-metric">
              <span>4 路</span>
              <p>视频矩阵</p>
            </article>
            <article className="hero-metric">
              <span>6 页</span>
              <p>完整产品页面</p>
            </article>
            <article className="hero-metric">
              <span>Mock + Live</span>
              <p>联调模式</p>
            </article>
          </div>
        </div>
      </section>

      <section className="login-panel">
        <div className="auth-card">
          <div className="auth-card__head">
            <p className="auth-card__eyebrow">Access Control</p>
            <h2>登录控制台</h2>
            <p>
              当前接口模式为 <strong>{apiConfig.mode}</strong>
              {apiConfig.baseUrl ? `，API: ${apiConfig.baseUrl}` : "，未配置 live API 时自动使用 mock"}
            </p>
          </div>

          <form
            className="auth-form"
            onSubmit={(event) => {
              event.preventDefault();
              setSubmitting(true);
              setError(undefined);
              void login({ username, password })
                .then(() => {
                  startTransition(() => {
                    navigate("/overview");
                  });
                })
                .catch((value) => {
                  setError(value instanceof Error ? value.message : "登录失败");
                })
                .finally(() => setSubmitting(false));
            }}
          >
            <label className="field">
              <span>账号</span>
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="请输入账号"
              />
            </label>
            <label className="field">
              <span>密码</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="请输入密码"
              />
            </label>

            {error ? <p className="form-error">{error}</p> : null}

            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? "登录中..." : "进入控制台"}
            </button>
          </form>

          <div className="demo-credentials">
            <p>Mock 演示账号</p>
            <span>`admin / FaceReco2026!`</span>
            <span>`operator / monitor2026`</span>
          </div>
        </div>
      </section>
    </div>
  );
}
