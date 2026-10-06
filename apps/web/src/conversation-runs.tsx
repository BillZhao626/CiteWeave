import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api, message, unwrap } from "./api";
import type { components } from "./generated/api";
import "./conversation-runs.css";

type Summary = components["schemas"]["ConversationRunSummary"];
export type Inspection = components["schemas"]["ConversationRunInspection"];
const short = (id: string) => id.slice(0, 12);
const date = (value: string | null) =>
  value
    ? new Date(value).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        hour12: false,
      })
    : "未记录";

export function ConversationRunSummary({ value }: { value: Inspection }) {
  const { run, trace } = value;
  const op = trace.operational;
  const metrics = [
    [
      "总耗时",
      op?.total.latency_ms == null
        ? "未记录"
        : `${(op.total.latency_ms / 1000).toFixed(2)} s`,
    ],
    ["持久事件", op ? String(op.timeline.length) : "未记录"],
    [
      "当前证据片段",
      trace.evidence_ids ? String(trace.evidence_ids.length) : "未记录",
    ],
    ["Provider 记录", op ? String(op.provider_phases.length) : "未记录"],
  ];
  return (
    <section className="conversation-run-summary" aria-label="所选会话运行摘要">
      <header>
        <div>
          <span className="eyebrow">PERSISTED RUN</span>
          <h2>运行摘要</h2>
        </div>
        <span className={`status ${run.status === "ACCEPTED" ? "good" : ""}`}>
          {run.status}
        </span>
      </header>
      <p className="run-summary-question">{trace.original_question}</p>
      <dl className="run-summary-identities">
        {[
          ["Conversation", run.conversation_id],
          ["Turn", run.turn_id],
          ["Run", run.id],
        ].map(([label, id]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{id}</dd>
          </div>
        ))}
      </dl>
      <div className="run-summary-metrics">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <small>{label}</small>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <footer>
        <span>
          准入 {date(run.created_at)} · 完成 {date(run.completed_at)}
        </span>
        <Link to={`/runtime/publication?run=${run.id}`}>检查发布记录 →</Link>
      </footer>
      {op?.truncated && (
        <p className="muted">
          事件计数来自最近的有界记录；不是完整运行事件总数。
        </p>
      )}
    </section>
  );
}

export function ConversationRunsPage() {
  const [params, setParams] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const catalog = useQuery({
    queryKey: ["conversation-run-catalog", offset],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/runtime/conversation-runs", {
          params: { query: { limit: 25, offset } },
        }),
      ),
  });
  const rows = catalog.data ?? [];
  const conversations = [...new Set(rows.map((r) => r.conversation_id))];
  const conversationId = params.get("conversation") ?? "";
  const visible = conversationId
    ? rows.filter((r) => r.conversation_id === conversationId)
    : rows;
  const requestedRun = params.get("run");
  const row = requestedRun
    ? visible.find((r) => r.run_id === requestedRun)
    : visible[0];
  const detail = useQuery({
    queryKey: ["publication-inspection", row?.conversation_id, row?.run_id],
    enabled: !!row,
    queryFn: async () =>
      unwrap(
        await api.GET(
          "/v1/conversations/{conversation_id}/runs/{run_id}/inspection",
          {
            params: {
              path: {
                conversation_id: row!.conversation_id,
                run_id: row!.run_id,
              },
            },
          },
        ),
      ),
  });
  const value = detail.data;
  const matches =
    !!row &&
    !!value &&
    value.run.id === row.run_id &&
    value.run.conversation_id === row.conversation_id &&
    value.run.turn_id === row.turn_id &&
    value.trace.run_id === row.run_id &&
    value.trace.conversation_id === row.conversation_id &&
    value.trace.turn_id === row.turn_id;
  const choose = (r: Summary) =>
    setParams({
      view: "conversation",
      ...(conversationId ? { conversation: conversationId } : {}),
      run: r.run_id,
    });
  return (
    <section className="ops-page conversation-runs-page">
      <p className="eyebrow">RUNTIME / CONVERSATION RUNS</p>
      <h1>会话运行记录</h1>
      <p className="muted ops-intro">
        按会话定位持久运行，检查每次请求的身份、状态与计量。
      </p>
      <div className="conversation-run-toolbar">
        <label>
          当前页会话{" "}
          <select
            aria-label="筛选已记录会话"
            value={conversationId}
            onChange={(e) =>
              setParams({
                view: "conversation",
                ...(e.target.value ? { conversation: e.target.value } : {}),
              })
            }
          >
            <option value="">全部会话</option>
            {conversations.map((id) => (
              <option key={id} value={id}>
                {short(id)} ·{" "}
                {rows.filter((r) => r.conversation_id === id).length} 条运行
              </option>
            ))}
          </select>
        </label>
        <span>{visible.length} 条当前页记录 · 只读</span>
      </div>
      {catalog.error && <p role="alert">{message(catalog.error)}</p>}
      {catalog.isPending && <p role="status">正在读取会话运行…</p>}
      {!catalog.error && !catalog.isPending && (
        <div className="ops-table-wrap conversation-run-table">
          <table>
            <thead>
              <tr>
                <th>Run / Turn</th>
                <th>本轮问题</th>
                <th>持久状态</th>
                <th>准入时间 · UTC+8</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.run_id} data-selected={row?.run_id === r.run_id}>
                  <td>
                    <button
                      aria-label={`查看运行 ${short(r.run_id)}`}
                      aria-pressed={row?.run_id === r.run_id}
                      onClick={() => choose(r)}
                    >
                      <strong>Run {short(r.run_id)}</strong>
                      <small>Turn {short(r.turn_id)}</small>
                    </button>
                  </td>
                  <td>{r.question}</td>
                  <td>
                    <span
                      className={`status ${r.status === "ACCEPTED" ? "good" : ""}`}
                    >
                      {r.status}
                    </span>
                    <small>
                      {r.publication === "PUBLISHED" ? "已发布" : "未发布"}
                    </small>
                  </td>
                  <td>{date(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!catalog.isPending && !catalog.error && !visible.length && (
        <p>当前页没有匹配的可访问会话运行。</p>
      )}
      {requestedRun && !catalog.isPending && !catalog.error && !row && (
        <p role="alert">所选 Run 不在当前页与会话范围内。</p>
      )}
      {detail.error && <p role="alert">{message(detail.error)}</p>}
      {row && detail.isPending && <p role="status">正在读取运行摘要…</p>}
      {!detail.error && value && !matches && (
        <p role="alert">运行摘要身份与所选记录不一致。</p>
      )}
      {!detail.error && value && matches && (
        <ConversationRunSummary value={value} />
      )}
      <div className="ops-pager">
        <button
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 25))}
        >
          上一页
        </button>
        <span>第 {offset / 25 + 1} 页 · 按准入时间倒序</span>
        <button
          disabled={rows.length < 25}
          onClick={() => setOffset(offset + 25)}
        >
          下一页
        </button>
      </div>
    </section>
  );
}
