import { useState } from "react";
import { Link, NavLink, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  CheckCheck,
  Clock3,
  GitMerge,
  LockKeyhole,
  ShieldCheck,
} from "lucide-react";
import { api, message, unwrap } from "./api";
import type { components } from "./generated/api";
import "./publication-inspector.css";

export type Inspection = components["schemas"]["ConversationRunInspection"];
type Summary = components["schemas"]["ConversationRunSummary"];
type TimelineItem = components["schemas"]["TimelineItem"];
const short = (value?: string | null) => (value ? value.slice(0, 8) : "无");
const date = (value: string) =>
  new Date(value).toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
  });
const time = (value: string) =>
  new Date(value).toLocaleTimeString("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
  });
const tone = (status: string) =>
  status === "ACCEPTED"
    ? "confirmed"
    : status === "UNKNOWN"
      ? "uncertain"
      : "withheld";
const outcomes: Record<string, string> = {
  ACCEPTED: "已确认成功",
  UNKNOWN: "结果未获确认",
  FAILED: "已记录失败",
  CANCELLED: "已取消",
  STALE: "过期尝试",
  INTERRUPTED: "执行中断",
  ADMITTED: "等待持久结果",
};
const reasons: Record<string, string> = {
  local_validation_failed: "本地结果校验未通过",
  conversation_context_overflow: "上下文超出运行边界",
  interpretation_history_unavailable: "解释结果所需历史不可用",
  cancel_requested: "收到取消请求",
  deadline_elapsed: "执行时限已到",
  execution_expired: "执行已过期",
};
const retryLabels: Record<string, string> = {
  BLOCKED_UNKNOWN: "自动重发已阻止",
  TERMINAL_NO_DISPATCH: "终态 · 不自动重发",
  EXPLICIT_NEW_AUTHORIZATION_REQUIRED: "需显式新授权",
  POLICY_AND_KNOWN_PROOF_REQUIRED: "须满足策略与已知结果证明",
};
const eventLabels: Record<string, string> = {
  admitted: "请求已准入",
  execution_started: "执行已开始",
  provider_completed: "上游响应已记录",
  provider_failure: "上游失败已记录",
  provider_retry: "已记录有限重试",
  accepted: "Acceptance 已提交",
  finished: "运行进入终态",
  cancelled: "取消已记录",
  recovered: "持久状态已恢复",
  stale_result_rejected: "迟到结果已拒绝",
  stage_failed: "阶段未通过",
  stage_completed: "阶段完成",
};
function Badge({ status }: { status: string }) {
  return <span className={`publication-badge ${tone(status)}`}>{status}</span>;
}
function Identity({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  return (
    <span className="publication-identity" title={value ?? "无"}>
      <small>{label}</small>
      <code>{short(value)}</code>
    </span>
  );
}
function IdentityDetails({ value }: { value: Inspection }) {
  return (
    <details className="publication-identities">
      <summary>完整身份与记录口径</summary>
      <dl>
        {[
          ["Conversation", value.run.conversation_id],
          ["Turn", value.run.turn_id],
          ["Run", value.run.id],
          ["Acceptance", value.publication.acceptance_id],
          ["Working State", value.publication.working_state?.snapshot_id],
          ["当前 head", value.publication.conversation_head_id],
        ].map(([label, id]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{id ?? "无"}</dd>
          </div>
        ))}
        <div>
          <dt>时间口径</dt>
          <dd>UTC+8；Acceptance 为持久记录时间，事件使用各自数据库时间戳。</dd>
        </div>
      </dl>
    </details>
  );
}
function InspectorHeader({
  reliability,
  runId,
}: {
  reliability: boolean;
  runId?: string;
}) {
  const selectedRun = runId ? `?run=${encodeURIComponent(runId)}` : "";
  return (
    <>
      <div className="publication-page-heading">
        <div>
          <p className="eyebrow">CONVERSATION / INSPECTOR</p>
          <h1>{reliability ? "可靠性决策" : "一致发布"}</h1>
        </div>
        <span className="publication-readonly">
          <LockKeyhole size={13} />
          只读 · 持久记录
        </span>
      </div>
      <nav className="publication-tabs" aria-label="会话检查视图">
        <NavLink to={`/runtime/publication${selectedRun}`}>
          Acceptance / 发布
        </NavLink>
        <NavLink to={`/runtime/reliability${selectedRun}`}>
          Run / 可靠性
        </NavLink>
      </nav>
    </>
  );
}
function useCatalog(offset: number) {
  return useQuery({
    queryKey: ["conversation-run-catalog", offset],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/runtime/conversation-runs", {
          params: { query: { limit: 25, offset } },
        }),
      ),
  });
}
function useInspection(row?: Summary) {
  return useQuery({
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
}
function PageState({
  pending,
  error,
  empty,
}: {
  pending: boolean;
  error: unknown;
  empty: boolean;
}) {
  if (error)
    return (
      <p className="error" role="alert">
        {message(error)}
      </p>
    );
  if (pending)
    return (
      <p className="muted" role="status">
        正在读取持久运行记录…
      </p>
    );
  if (empty) return <p className="muted">当前页没有可访问的会话运行。</p>;
  return null;
}
function Pager({
  offset,
  count,
  change,
}: {
  offset: number;
  count: number;
  change: (n: number) => void;
}) {
  return (
    <footer className="publication-page-footer">
      <span>
        第 {offset / 25 + 1} 页 · {count} 条持久记录 · 按准入时间倒序
      </span>
      <div>
        <button
          disabled={offset === 0}
          onClick={() => change(Math.max(0, offset - 25))}
        >
          上一页
        </button>
        <button disabled={count < 25} onClick={() => change(offset + 25)}>
          下一页
        </button>
      </div>
    </footer>
  );
}
export function PublicationView({ value }: { value: Inspection }) {
  const [expanded, setExpanded] = useState(false);
  const { run, publication, trace } = value;
  const accepted = run.accepted;
  const state = publication.working_state;
  const published =
    publication.decision === "PUBLISHED" &&
    !!accepted &&
    !!state &&
    accepted.acceptance_id === state.snapshot_id;
  const events =
    trace.operational?.timeline.filter(
      (e) =>
        e.kind === "accepted" ||
        (e.phase === "publication" && e.kind === "stage_completed"),
    ) ?? [];
  return (
    <>
      <div className="publication-context">
        <p>{trace.original_question}</p>
        <div>
          <Identity label="Conversation" value={run.conversation_id} />
          <Identity label="Turn" value={run.turn_id} />
          <Identity label="Run" value={run.id} />
          <Badge status={run.status} />
        </div>
      </div>
      {published ? (
        <>
          <div className="publication-banner">
            <div className="publication-banner-icon">
              <CheckCheck size={29} />
            </div>
            <div>
              <small>ACCEPTANCE · {short(publication.acceptance_id)}</small>
              <h2>答案与下一轮状态，已一起发布。</h2>
            </div>
            <div className="publication-banner-time">
              <span>
                <Check size={14} />
                已接受
              </span>
              <small>{date(publication.recorded_at!)}</small>
            </div>
          </div>
          <div className="publication-bundle">
            <article className="publication-card">
              <header>
                <span className="publication-card-number">01</span>
                <h3>正式答案</h3>
                <span className="publication-card-status">
                  <Check size={13} />
                  已发布
                </span>
              </header>
              <p className={`publication-answer ${expanded ? "expanded" : ""}`}>
                {accepted.result.text}
              </p>
              <button
                className="publication-expand-answer"
                aria-expanded={expanded}
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? "收起答案" : "查看完整答案"}
              </button>
              <footer>
                <span>
                  {accepted.result.kind === "documentary_answer"
                    ? `${accepted.result.citations.length} 条绑定引用`
                    : accepted.result.kind === "clarification"
                      ? "澄清结果"
                      : "证据不足结果"}
                </span>
                <Identity label="Acceptance" value={accepted.acceptance_id} />
              </footer>
            </article>
            <article className="publication-card">
              <header>
                <span className="publication-card-number">02</span>
                <h3>Working State</h3>
                <span className="publication-card-status">
                  <Check size={13} />
                  已发布
                </span>
              </header>
              <div className="publication-state-body">
                <small>本轮持久主题信号</small>
                <p>{state.topic_signal ?? "此快照未记录主题信号"}</p>
                <dl>
                  <div>
                    <dt>状态版本</dt>
                    <dd>{state.revision}</dd>
                  </div>
                  <div>
                    <dt>来源 Turn</dt>
                    <dd title={state.source_turn_id}>
                      {short(state.source_turn_id)}
                    </dd>
                  </div>
                  <div>
                    <dt>前序快照</dt>
                    <dd title={state.previous_snapshot_id ?? "无"}>
                      {short(state.previous_snapshot_id)}
                    </dd>
                  </div>
                  <div>
                    <dt>活动 / 已退役条目</dt>
                    <dd>
                      {state.active_entries ?? "未记录"} /{" "}
                      {state.retired_entries ?? "未记录"}
                    </dd>
                  </div>
                </dl>
                <span className="publication-context-note">
                  用于理解下一轮请求 · 文档证据仍需重新检索
                </span>
              </div>
              <footer>
                <span>不可变状态快照</span>
                <Identity label="Acceptance" value={state.snapshot_id} />
              </footer>
            </article>
          </div>
          <div
            className={`publication-head ${publication.head_relation === "CURRENT" ? "current" : "advanced"}`}
          >
            <GitMerge size={23} />
            <div>
              <h3>
                {publication.head_relation === "CURRENT"
                  ? "Conversation head 指向同一份 Acceptance"
                  : "后续轮次已推进 Conversation head"}
              </h3>
              <p>
                {publication.head_relation === "CURRENT"
                  ? "下一轮从这份已接受的状态继续。"
                  : "本次结果仍是已发布的历史结果；下一轮使用当前 head。"}
              </p>
            </div>
            <Identity
              label="当前 head"
              value={publication.conversation_head_id}
            />
            <span>
              {publication.head_relation === "CURRENT"
                ? "身份一致"
                : "历史 Acceptance"}
            </span>
          </div>
          <div className="publication-event-strip">
            <Clock3 size={15} />
            <span>持久发布事件</span>
            {events.length ? (
              events.map((e) => (
                <span key={e.id}>
                  <strong>{time(e.created_at)}</strong>{" "}
                  {e.kind === "accepted"
                    ? "ADMITTED → ACCEPTED"
                    : "一致发布完成"}
                </span>
              ))
            ) : (
              <span>此历史记录未采集发布事件</span>
            )}
          </div>
        </>
      ) : (
        <div className="publication-unpublished">
          <ShieldCheck size={28} />
          <h2>本次运行没有正式发布结果</h2>
          <p>未绑定本次 Run 的 Acceptance；答案与 Working State 均未发布。</p>
          <Identity
            label="当前 head"
            value={publication.conversation_head_id}
          />
        </div>
      )}
      <IdentityDetails value={value} />
    </>
  );
}
export function PublicationPage() {
  const [offset, setOffset] = useState(0);
  const [params, setParams] = useSearchParams();
  const catalog = useCatalog(offset);
  const rows = catalog.data ?? [];
  const requestedRun = params.get("run");
  const row = requestedRun
    ? rows.find((r) => r.run_id === requestedRun)
    : (rows.find((r) => r.status === "ACCEPTED") ?? rows[0]);
  const detail = useInspection(row);
  return (
    <section className="publication-page publication-acceptance-page">
      <InspectorHeader reliability={false} runId={row?.run_id} />
      <div className="publication-toolbar">
        <label htmlFor="publication-run">运行记录</label>
        <select
          id="publication-run"
          value={row?.run_id ?? ""}
          onChange={(e) => setParams({ run: e.target.value })}
        >
          {rows.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.status} · {short(r.run_id)} · {r.question}
            </option>
          ))}
        </select>
        <Link
          to={
            row
              ? `/runtime/reliability?run=${encodeURIComponent(row.run_id)}`
              : "/runtime/reliability"
          }
        >
          查看可靠性决策 <ArrowRight size={14} />
        </Link>
      </div>
      <PageState
        pending={catalog.isPending || (!!row && detail.isPending)}
        error={catalog.error ?? detail.error}
        empty={!catalog.isPending && rows.length === 0}
      />
      {requestedRun && !catalog.isPending && !catalog.error && !row && (
        <p role="alert">所选 Run 不在当前页可访问记录中。</p>
      )}
      {!detail.error && detail.data && (
        <PublicationView key={detail.data.run.id} value={detail.data} />
      )}
      <Pager offset={offset} count={rows.length} change={setOffset} />
    </section>
  );
}
export function ReliabilityView({ value }: { value: Inspection }) {
  const { trace, run, publication } = value;
  const op = trace.operational;
  const failed = [...(op?.timeline ?? [])].reverse().find((e) => e.error_code);
  const evidence =
    op?.timeline.filter((e) =>
      [
        "admitted",
        "execution_started",
        "provider_completed",
        "provider_failure",
        "provider_retry",
        "stage_failed",
        "accepted",
        "finished",
        "cancelled",
        "recovered",
        "stale_result_rejected",
      ].includes(e.kind),
    ) ?? [];
  const descriptions: Record<string, string> = {
    KNOWN_RESULT_NOT_ACCEPTED:
      "上游响应已记录；后续处理未通过，未形成 Acceptance。",
    PROVIDER_UNCERTAIN: "上游执行结果无法确认；未形成 Acceptance。",
    CANCELLED_WITH_UNRESOLVED_PROVIDER: "取消已记录；上游结果仍未解决。",
    LEGACY_REASON_UNAVAILABLE: "历史记录不足以确认原因；保持 UNKNOWN。",
  };
  return (
    <article className={`reliability-detail ${tone(run.status)}`}>
      <header>
        <div>
          <small>RUN DECISION</small>
          <h2>{outcomes[run.status]}</h2>
        </div>
        <Badge status={run.status} />
      </header>
      <p className="reliability-question">{trace.original_question}</p>
      <div className="reliability-identity-row">
        <Identity label="Run" value={run.id} />
        <span>{date(run.created_at)}</span>
      </div>
      <div className="reliability-decisions">
        <div>
          <LockKeyhole size={17} />
          <small>重发决策</small>
          <strong>{op ? retryLabels[op.retry_decision] : "未记录决策"}</strong>
          <code>{op?.retry_decision ?? "UNAVAILABLE"}</code>
        </div>
        <div>
          <ShieldCheck size={17} />
          <small>发布决策</small>
          <strong>
            {publication.decision === "PUBLISHED"
              ? "正式结果已发布"
              : "无正式结果发布"}
          </strong>
          <code>
            {publication.decision === "PUBLISHED"
              ? `Acceptance ${short(publication.acceptance_id)}`
              : "NO ACCEPTANCE"}
          </code>
        </div>
      </div>
      <div className="reliability-reason">
        <strong>
          {failed?.error_code
            ? (reasons[failed.error_code] ?? failed.error_code)
            : run.status === "ACCEPTED"
              ? "结果已通过 Acceptance 边界"
              : "详细失败原因未记录"}
        </strong>
        <p>
          {op?.unknown_reason
            ? descriptions[op.unknown_reason]
            : publication.decision === "PUBLISHED"
              ? "答案与会话状态绑定同一份已接受结果。"
              : "保留运行记录；本次 Run 没有已接受结果。"}
        </p>
        {failed?.error_code && <code>{failed.error_code}</code>}
      </div>
      <div className="reliability-timeline-heading">
        <h3>持久事件</h3>
        <span>UTC+8 · 记录顺序</span>
      </div>
      {evidence.length ? (
        <ol className="reliability-timeline" aria-label="可靠性持久事件">
          {evidence.map((e: TimelineItem) => (
            <li key={e.id}>
              <time>{time(e.created_at)}</time>
              <span className="reliability-event-dot" />
              <div>
                <strong>{eventLabels[e.kind] ?? e.kind}</strong>
                <small>
                  {e.error_code
                    ? (reasons[e.error_code] ?? e.error_code)
                    : (e.to_state ?? e.phase ?? e.kind)}
                </small>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">此历史记录未采集事件，不重建执行过程。</p>
      )}
      {op?.truncated && (
        <p className="muted">事件列表已截断；仅显示最近的有界记录。</p>
      )}
      <IdentityDetails value={value} />
    </article>
  );
}
export function ReliabilityPage() {
  const [offset, setOffset] = useState(0),
    [all, setAll] = useState(false);
  const [params, setParams] = useSearchParams();
  const catalog = useCatalog(offset);
  const rows = catalog.data ?? [];
  const representatives = rows.filter(
    (r, i) => rows.findIndex((v) => v.status === r.status) === i,
  );
  const requestedRun = params.get("run");
  const requestedRow = rows.find((r) => r.run_id === requestedRun);
  const visible = all
    ? rows
    : requestedRow && !representatives.some((r) => r.run_id === requestedRun)
      ? [...representatives, requestedRow]
      : representatives;
  const row = requestedRun
    ? rows.find((r) => r.run_id === requestedRun)
    : (visible.find((r) => r.status === "ACCEPTED") ?? visible[0]);
  const detail = useInspection(row);
  return (
    <section className="publication-page">
      <InspectorHeader reliability runId={row?.run_id} />
      <div className="reliability-policy">
        <ShieldCheck size={26} />
        <div>
          <h2>只发布已经确认的结果。</h2>
          <span>ACCEPTED 发布正式结果 · UNKNOWN 保留记录并阻止自动重发</span>
        </div>
        <small>POSTGRESQL / DURABLE TRUTH</small>
      </div>
      <PageState
        pending={catalog.isPending}
        error={catalog.error}
        empty={!catalog.isPending && rows.length === 0}
      />
      <div className="reliability-split">
        <div className="reliability-records">
          <header>
            <h3>已记录的运行状态</h3>
            <button onClick={() => setAll(!all)}>
              {all ? "各状态最近一条" : "全部运行"}
            </button>
          </header>
          <p className="reliability-list-note">
            {all
              ? "当前页全部持久记录"
              : requestedRow &&
                  !representatives.some((r) => r.run_id === requestedRun)
                ? "当前页各状态最近一次及所选运行"
                : "当前页每种状态最近的一次运行"}
          </p>
          {visible.map((r) => (
            <button
              className={`reliability-record ${tone(r.status)}`}
              key={r.run_id}
              aria-pressed={row?.run_id === r.run_id}
              onClick={() => setParams({ run: r.run_id })}
            >
              <div>
                <Badge status={r.status} />
                <span>{outcomes[r.status]}</span>
              </div>
              {r.status === "ACCEPTED" ? (
                <p>{r.question}</p>
              ) : (
                <p className="reliability-secondary-reason">
                  {r.reason_code
                    ? (reasons[r.reason_code] ?? r.reason_code)
                    : "原因未记录"}
                </p>
              )}
              <div className="reliability-record-decisions">
                <span>
                  {r.publication === "PUBLISHED"
                    ? "✓ 已发布"
                    : "未发布 · 无 Acceptance"}
                </span>
                <span>{retryLabels[r.retry_decision]}</span>
              </div>
              <footer>
                <code>Run {short(r.run_id)}</code>
                <span>{date(r.created_at)}</span>
              </footer>
            </button>
          ))}
          <p className="reliability-list-note">
            仅展示真实已有状态；记录缺失时不补造示例。
          </p>
        </div>
        <div>
          {requestedRun && !catalog.isPending && !catalog.error && !row && (
            <p role="alert">所选 Run 不在当前页可访问记录中。</p>
          )}
          <PageState
            pending={!!row && detail.isPending}
            error={detail.error}
            empty={false}
          />
          {!detail.error && detail.data && (
            <ReliabilityView value={detail.data} />
          )}
        </div>
      </div>
      <Pager offset={offset} count={rows.length} change={setOffset} />
    </section>
  );
}
