import { useDeferredValue, useMemo, useState } from "react";

import { Panel } from "../components/Panel";
import { MetricCard } from "../components/MetricCard";
import { StateBlock } from "../components/StateBlock";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { api } from "../lib/api/client";
import { formatDate, formatDateTime, toDateInputValue } from "../lib/format";

export function LogsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("任何状态");
  const [attendanceType, setAttendanceType] = useState("任何类型");
  const [startDate, setStartDate] = useState(toDateInputValue(-1));
  const [endDate, setEndDate] = useState(toDateInputValue(0));
  const deferredSearch = useDeferredValue(search);

  const logsResource = useAsyncResource(
    () =>
      api.getLogs({
        search: deferredSearch,
        status,
        attendance_type: attendanceType,
        start_time: startDate,
        end_time: endDate,
      }),
    [deferredSearch, status, attendanceType, startDate, endDate],
    { pollMs: 18_000 },
  );

  const attendanceResource = useAsyncResource(
    () =>
      api.getAttendance({
        search: deferredSearch,
        status,
        start_time: startDate,
        end_time: endDate,
      }),
    [deferredSearch, status, startDate, endDate],
    { pollMs: 18_000 },
  );

  const logs = useMemo(() => logsResource.data ?? [], [logsResource.data]);
  const attendance = useMemo(
    () => attendanceResource.data ?? [],
    [attendanceResource.data],
  );

  const summary = useMemo(() => {
    const abnormalCount = logs.filter((item) => item.status === "异常").length;
    const uniquePeople = new Set(logs.map((item) => item.person_name)).size;
    const avgConfidence =
      logs.length > 0
        ? logs.reduce((sum, item) => sum + item.confidence, 0) / logs.length
        : 0;
    return { abnormalCount, uniquePeople, avgConfidence };
  }, [logs]);

  return (
    <div className="page-grid">
      <div className="metric-grid">
        <MetricCard
          label="当前日志条数"
          value={`${logs.length}`}
          helper="基于当前筛选条件"
        />
        <MetricCard
          label="异常记录"
          value={`${summary.abnormalCount}`}
          helper="陌生人或异常考勤"
          tone="warning"
        />
        <MetricCard
          label="覆盖人员"
          value={`${summary.uniquePeople}`}
          helper="筛选结果中的不同人员"
        />
        <MetricCard
          label="平均置信度"
          value={`${Math.round(summary.avgConfidence * 100)}%`}
          helper="越高越稳定"
          tone="accent"
        />
      </div>

      <Panel
        eyebrow="Audit Filters"
        title="日志与考勤"
        subtitle="支持关键字、时间和状态过滤，同时保留空状态和加载状态。"
      >
        <div className="filter-bar">
          <input
            className="toolbar-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索姓名、地点、情绪或状态"
          />
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option>任何状态</option>
            <option>正常</option>
            <option>迟到</option>
            <option>早退</option>
            <option>已记录</option>
            <option>异常</option>
          </select>
          <select
            value={attendanceType}
            onChange={(event) => setAttendanceType(event.target.value)}
          >
            <option>任何类型</option>
            <option>上班打卡</option>
            <option>下班打卡</option>
            <option>外出登记</option>
            <option>重复识别</option>
            <option>未识别</option>
          </select>
          <input
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
          <input
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
        </div>

        <div className="table-layout">
          <div className="data-table-card">
            <div className="data-table-card__head">
              <h3>识别日志</h3>
              <span>{logs.length} 条</span>
            </div>
            {logsResource.loading && !logs.length ? (
              <StateBlock
                title="正在查询日志"
                description="等待 GET /api/logs 返回筛选结果。"
              />
            ) : logs.length ? (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>姓名</th>
                      <th>地点</th>
                      <th>时间</th>
                      <th>情绪</th>
                      <th>考勤类型</th>
                      <th>状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((record) => (
                      <tr key={record.id}>
                        <td>{record.person_name}</td>
                        <td>{record.location}</td>
                        <td>{formatDateTime(record.captured_at)}</td>
                        <td>{record.emotion}</td>
                        <td>{record.attendance_type}</td>
                        <td>{record.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <StateBlock
                title="没有匹配日志"
                description="当前筛选条件下没有数据，请放宽条件重新查询。"
              />
            )}
          </div>

          <div className="data-table-card">
            <div className="data-table-card__head">
              <h3>考勤概览</h3>
              <span>{attendance.length} 人</span>
            </div>
            {attendanceResource.loading && !attendance.length ? (
              <StateBlock
                title="正在查询考勤"
                description="等待 GET /api/attendance 返回汇总结果。"
              />
            ) : attendance.length ? (
              <div className="attendance-list">
                {attendance.map((item) => (
                  <article key={item.id} className="attendance-item">
                    <div>
                      <strong>{item.name}</strong>
                      <p>
                        {formatDate(item.date)} · {item.location}
                      </p>
                    </div>
                    <div className="attendance-item__tail">
                      <span>{item.attendance_type}</span>
                      <strong>{item.status}</strong>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <StateBlock
                title="当前没有考勤结果"
                description="当 attendance 接口为空时，这里会显示明确提示。"
              />
            )}
          </div>
        </div>
      </Panel>
    </div>
  );
}
