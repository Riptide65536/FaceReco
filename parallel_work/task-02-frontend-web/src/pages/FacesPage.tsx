import { useDeferredValue, useMemo, useState } from "react";

import { useShellContext } from "../app/useShellContext";
import { Panel } from "../components/Panel";
import { StateBlock } from "../components/StateBlock";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { api } from "../lib/api/client";
import { formatRelativeTime } from "../lib/format";

function qualityTone(quality: string) {
  switch (quality) {
    case "excellent":
      return "success";
    case "warning":
      return "warning";
    default:
      return "info";
  }
}

export function FacesPage() {
  const { apiMode } = useShellContext();
  const facesResource = useAsyncResource(() => api.getFaceLibrary(), [], {
    pollMs: 20_000,
  });
  const [query, setQuery] = useState("");
  const [newName, setNewName] = useState("");
  const [newDepartment, setNewDepartment] = useState("");
  const [newTags, setNewTags] = useState("");
  const [feedback, setFeedback] = useState<string | undefined>();
  const deferredQuery = useDeferredValue(query);

  const faces = useMemo(
    () =>
      (facesResource.data ?? []).filter((face) =>
        [face.name, face.department, face.tags.join(" ")]
          .join(" ")
          .toLowerCase()
          .includes(deferredQuery.toLowerCase()),
      ),
    [deferredQuery, facesResource.data],
  );

  return (
    <div className="page-grid">
      <Panel
        eyebrow="Registry Workspace"
        title="人脸库管理"
        subtitle="强调样本质量、最近活动和重点关注状态，不再只是一张静态列表。"
        actions={
          <input
            className="toolbar-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索姓名、部门或标签"
          />
        }
      >
        <div className="callout-banner">
          <strong>接口说明</strong>
          <p>
            当前人脸库列表在 {apiMode} 模式下会优先尝试真实接口；若 Task-01 尚未提供
            `GET /api/faces`，则自动退回 mock 演示。
          </p>
        </div>

        <div className="face-workspace">
          <form
            className="face-form"
            onSubmit={(event) => {
              event.preventDefault();
              setFeedback(undefined);
              if (!newName || !newDepartment) {
                setFeedback("请先填写姓名和部门。");
                return;
              }
              void api
                .registerFace({
                  name: newName,
                  department: newDepartment,
                  tags: newTags
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                })
                .then((result) => {
                  setFeedback(result.message);
                  setNewName("");
                  setNewDepartment("");
                  setNewTags("");
                  return facesResource.refresh();
                })
                .catch((value) => {
                  setFeedback(
                    value instanceof Error ? value.message : "新增人脸失败",
                  );
                });
            }}
          >
            <h3>录入演示入口</h3>
            <label className="field">
              <span>姓名</span>
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                placeholder="例如：张宁"
              />
            </label>
            <label className="field">
              <span>部门</span>
              <input
                value={newDepartment}
                onChange={(event) => setNewDepartment(event.target.value)}
                placeholder="例如：运营中心"
              />
            </label>
            <label className="field">
              <span>标签</span>
              <input
                value={newTags}
                onChange={(event) => setNewTags(event.target.value)}
                placeholder="多个标签请用英文逗号分隔"
              />
            </label>
            <button className="primary-button" type="submit">
              新增示例档案
            </button>
            {feedback ? <p className="inline-feedback">{feedback}</p> : null}
          </form>

          <div className="face-grid">
            {facesResource.loading && !faces.length ? (
              <StateBlock
                title="正在加载人脸库"
                description="等待真实接口返回，或切换到 mock 演示数据。"
              />
            ) : faces.length ? (
              faces.map((face) => (
                <article key={face.id} className="face-card">
                  <div className="face-card__head">
                    <div className="face-avatar">
                      {face.name.slice(0, 1)}
                    </div>
                    <div>
                      <h3>{face.name}</h3>
                      <p>{face.department}</p>
                    </div>
                    <StatusBadge
                      label={face.quality}
                      tone={qualityTone(face.quality)}
                      compact
                    />
                  </div>
                  <div className="face-card__metrics">
                    <span>{face.sample_count} 样本</span>
                    <span>{formatRelativeTime(face.last_seen_at)}</span>
                    <span>{face.watchlist ? "重点关注" : "普通档案"}</span>
                  </div>
                  <div className="tag-row">
                    {face.tags.map((tag) => (
                      <span key={tag} className="tag-chip">
                        {tag}
                      </span>
                    ))}
                  </div>
                  <button
                    className="ghost-button"
                    onClick={() => {
                      void api.deleteFace(face.name).then(async (result) => {
                        setFeedback(result.message);
                        await facesResource.refresh();
                      });
                    }}
                  >
                    删除档案
                  </button>
                </article>
              ))
            ) : (
              <StateBlock
                title="当前没有档案"
                description="空状态也会保持页面结构，不会突然塌成一块白板。"
              />
            )}
          </div>
        </div>
      </Panel>
    </div>
  );
}
