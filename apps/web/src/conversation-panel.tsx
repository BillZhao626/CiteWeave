import { useEffect, useState, useSyncExternalStore } from "react";
import type { Citation, Doc } from "./api";
import { Button } from "./components/ui/button";
import { CitationText } from "./citation-text";
import { PdfEvidence } from "./pdf-evidence";
import {
  ConversationSession,
  type ConversationTrace,
  type PublicRun,
} from "./conversation-session";
import "./conversation.css";
import { CitationStatus } from "./citation-status";
import { RunOverview } from "./run-overview";

const labels: Record<PublicRun["status"], string> = {
  ADMITTED: "已准入，等待持久结果",
  ACCEPTED: "已接受",
  FAILED: "执行失败，未接受答案",
  CANCELLED: "已取消，未接受答案",
  INTERRUPTED: "执行中断，未接受答案",
  UNKNOWN: "执行结果未知，未接受答案",
  STALE: "尝试已过期，未接受答案",
};
export function AcceptedAnswer({
  run,
  selected,
  onSelect,
}: {
  run: PublicRun;
  selected: Citation | null;
  onSelect: (citation: Citation) => void;
}) {
  const result = run.status === "ACCEPTED" ? run.accepted?.result : null;
  if (!result) return <p className="muted">尚无此 Run 的已接受结果。</p>;
  if (result.kind === "clarification")
    return (
      <div>
        <strong>需要澄清</strong>
        <p className="answer-text">{result.text}</p>
        <p className="muted">可以在下方直接补充说明。</p>
      </div>
    );
  if (result.kind === "evidence_insufficient")
    return (
      <div>
        <strong>当前授权证据不足</strong>
        <p className="answer-text">{result.text}</p>
        <p className="muted">此结果没有可作为支持的文档引用。</p>
      </div>
    );
  return (
    <div>
      <strong>文档答案</strong>
      <div className="answer-text">
        <CitationText
          text={result.text}
          citations={result.citations}
          selected={selected}
          onSelect={onSelect}
        />
      </div>
      <CitationStatus hasCitations={result.citations.length > 0} />
      <div className="citation-cards">
        {result.citations.map((citation) => (
          <button
            key={`${citation.document_version_id}:${citation.evidence_id}:${citation.label}`}
            className="citation-card"
            onClick={() => onSelect(citation)}
          >
            <span className="citation-index">{citation.label}</span>
            <div>
              <strong>{citation.filename}</strong>
              <p>{citation.span.quote}</p>
              <small>
                第 {citation.span.boxes[0].page_index + 1} 页 · 查看原文 ↗
              </small>
            </div>
          </button>
        ))}
      </div>
      <details className="source-details">
        <summary>答案的文档身份</summary>
        {result.documents.map((doc) => (
          <p key={doc.document_version_id} className="version-meta">
            文档 {doc.document_id}
            <br />
            版本 {doc.document_version_id}
          </p>
        ))}
      </details>
    </div>
  );
}

const traceFields: [keyof ConversationTrace, string][] = [
  ["revision", "Trace 契约"],
  ["conversation_id", "会话"],
  ["turn_id", "Turn"],
  ["run_id", "Run"],
  ["retry_of", "前次尝试"],
  ["status", "持久状态"],
  ["created_at", "创建时间"],
  ["completed_at", "完成时间"],
  ["input_head_id", "输入 head"],
  ["acceptance_id", "接受记录"],
  ["output_state_id", "输出状态身份"],
  ["original_question", "原始问题"],
  ["scope", "本次明确范围"],
  ["metadata_availability", "元数据可用性"],
  ["interpretation_mode", "解释模式"],
  ["interpretation_identity", "解释身份"],
  ["selected_query", "实际检索问题"],
  ["history_sources", "历史来源身份（非证据）"],
  ["input_state_item_ids", "输入状态项身份"],
  ["retrieval_profile", "检索配置"],
  ["documents", "文档与版本"],
  ["evidence_pack_identity", "证据包身份"],
  ["evidence_ids", "Evidence 身份"],
  ["citations", "Citation 身份"],
  ["validation", "引用物理校验"],
  ["semantic_support", "语义支持评估"],
];
function ContextEvidenceSummary({ trace }: { trace: ConversationTrace }) {
  if (trace.metadata_availability !== "documentary_bundle") return null;
  return (
    <div className="context-evidence-summary" aria-label="上下文与当前证据">
      <div>
        <span>上下文理解</span>
        <strong>
          {trace.history_sources == null
            ? "历史来源未记录"
            : `${trace.history_sources.length} 轮历史用于解释`}
        </strong>
        {!!trace.input_state_item_ids?.length && (
          <small>{trace.input_state_item_ids.length} 个工作状态项</small>
        )}
      </div>
      <div>
        <span>当前轮检索</span>
        <strong>
          {trace.evidence_ids == null
            ? "证据数量未记录"
            : `${trace.evidence_ids.length} 个当前证据片段`}
        </strong>
        <small>文档原文作为回答依据</small>
      </div>
      {trace.selected_query && (
        <details
          className="selected-query"
          open={!!trace.history_sources?.length || undefined}
        >
          <summary>实际检索问题</summary>
          <p>{trace.selected_query}</p>
        </details>
      )}
    </div>
  );
}
export function TraceInspector({ trace }: { trace?: ConversationTrace }) {
  return (
    <details className="trace conversation-trace">
      <summary>Trace Inspector · 持久记录</summary>
      <details>
        <summary>引用与计量说明</summary>
        <p>
          CURRENT_PACK_PHYSICAL_ONLY ≠ semantic
          support。物理引用校验不证明语义支持。
        </p>
      </details>
      {!trace ? (
        <p>未记录 / 不可用</p>
      ) : (
        <>
          <dl className="trace-identity" aria-label="运行身份">
            <div>
              <dt>Conversation</dt>
              <dd>{trace.conversation_id}</dd>
            </div>
            <div>
              <dt>Turn</dt>
              <dd>{trace.turn_id}</dd>
            </div>
            <div>
              <dt>Run</dt>
              <dd>{trace.run_id}</dd>
            </div>
          </dl>
          <OperationalTimeline trace={trace} />
          <details>
            <summary>完整 Trace 字段</summary>
            <dl>
              {traceFields.map(([field, label]) => (
                <div key={field}>
                  <dt>{label}</dt>
                  <dd>
                    {trace[field] == null ? (
                      "未记录 / 不可用"
                    ) : typeof trace[field] === "object" ? (
                      <pre>{JSON.stringify(trace[field], null, 2)}</pre>
                    ) : (
                      String(trace[field])
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        </>
      )}
    </details>
  );
}

export function OperationalTimeline({ trace }: { trace: ConversationTrace }) {
  const operational = trace.operational;
  if (!operational) return <p>运行时间线：未记录 / 不可用</p>;
  const duration = (value: number | null | undefined) =>
    value == null ? "未记录 / 不可用" : `${value} ms`;
  return (
    <section aria-label="运行时间线">
      <RunOverview trace={trace} />
      <h4>运行时间线 · {trace.status}</h4>
      <p>
        发布：{operational.publication} · 重试：{operational.retry_decision}
      </p>
      {operational.unknown_reason && (
        <p>UNKNOWN 原因：{operational.unknown_reason}</p>
      )}
      {operational.timeline
        .filter((event) => event.error_code)
        .slice(-1)
        .map((event) => (
          <p key={event.id} className="error">
            运行错误：{event.error_category ?? "未分类"} · {event.error_code}
          </p>
        ))}
      <p>
        总时长：{duration(operational.total.latency_ms)} ·{" "}
        {operational.total.availability}
      </p>
      {operational.truncated && (
        <p role="status">仅显示最近 64 条持久事件；阶段时长可能不完整。</p>
      )}
      <table className="trace-durations">
        <thead>
          <tr>
            <th>阶段</th>
            <th>耗时</th>
            <th>记录状态</th>
          </tr>
        </thead>
        <tbody>
          {operational.durations.map((item) => (
            <tr key={item.phase}>
              <td>{item.phase}</td>
              <td>{duration(item.latency_ms)}</td>
              <td>{item.availability}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">阶段耗时可重叠；publication 不含 commit 确认。</p>
      {operational.provider_phases
        .filter((p) => p.error_code)
        .map((p) => (
          <p key={p.provider_phase_id} className="error">
            {p.phase} · {p.error_category ?? "未分类"} · {p.error_code}
          </p>
        ))}
      <details>
        <summary>持久事件 · {operational.timeline.length} 条</summary>
        <ol className="operational-timeline">
          {operational.timeline.map((event) => (
            <li key={event.id}>
              <time dateTime={event.created_at}>{event.created_at}</time>
              <strong>
                {event.kind} · {event.phase ?? "Run"}
              </strong>
              <span>
                attempt {event.attempt ?? "未记录"} · fence {event.fence}
                {event.current_fence != null &&
                  ` → 当前 ${event.current_fence}`}
              </span>
              {(event.from_state || event.to_state) && (
                <span>
                  {event.from_state ?? "未记录"} → {event.to_state ?? "未记录"}
                </span>
              )}
              {event.retry_classification && (
                <span>重试分类：{event.retry_classification}</span>
              )}
              {event.error_code && (
                <span>
                  {event.error_category ?? "未分类"} · {event.error_code}
                </span>
              )}
              {event.latency_ms != null && (
                <span>{duration(event.latency_ms)}</span>
              )}
            </li>
          ))}
        </ol>
      </details>
      <details>
        <summary>阶段时长与 Provider 回执</summary>
        <p>
          阶段时长可重叠；发布阶段截至最后 flush 前，排除 commit 确认。dispatch
          标记先于网络发送提交。
        </p>
        <dl>
          {operational.durations.map((item) => (
            <div key={item.phase}>
              <dt>{item.phase}</dt>
              <dd>
                {duration(item.latency_ms)} · {item.availability} ·{" "}
                {item.measurement}
              </dd>
            </div>
          ))}
        </dl>
        {operational.provider_phases.map((phase) => (
          <div key={phase.provider_phase_id}>
            <p>
              {phase.phase} · {phase.state} · {phase.dispatch}
            </p>
            <p>
              attempt {phase.attempt ?? "未记录"} / {phase.attempt_limit} ·{" "}
              {phase.retry_classification ?? "未记录"}
            </p>
            <p>
              usage：
              {phase.usage == null
                ? "未记录 / 不可用"
                : JSON.stringify(phase.usage)}
            </p>
            <p>
              估算费用：{phase.estimated_yuan ?? "未记录 / 不可用"} CNY ·{" "}
              {phase.price_revision ?? "未记录"}（非账单）
            </p>
          </div>
        ))}
      </details>
    </section>
  );
}

export function ConversationPanel({
  kbId,
  docs,
  selected,
  onSelect,
  session: suppliedSession,
}: {
  kbId: string;
  docs: Doc[];
  selected: Citation | null;
  onSelect: (citation: Citation | null) => void;
  session?: ConversationSession;
}) {
  const [session] = useState(
    () =>
      suppliedSession ??
      new ConversationSession(kbId, {
        getItem: (key) => window.sessionStorage.getItem(key),
        setItem: (key, value) => window.sessionStorage.setItem(key, value),
      }),
  );
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const [question, setQuestion] = useState("");
  const [existingConversation, setExistingConversation] = useState("");
  const [existingRuns, setExistingRuns] = useState("");
  const [focusedRunId, setFocusedRunId] = useState<string | null>(null);
  const [view, setView] = useState<"answer" | "trace">("answer");
  useEffect(() => {
    void session.refresh();
  }, [session]);
  useEffect(() => {
    if (!state.conversation && selected) onSelect(null);
  }, [state.conversation, selected, onSelect]);
  const pendingRun = state.runs.some((run) => run.status === "ADMITTED");
  const turnIds = [...new Set(state.runs.map((run) => run.turn_id))];
  const focusedRun =
    state.runs.find((run) => run.id === focusedRunId) ?? state.runs.at(-1);
  const focusedTrace = focusedRun ? state.traces[focusedRun.id] : undefined;
  const focusedNumber = focusedRun
    ? turnIds.indexOf(focusedRun.turn_id) + 1
    : 0;
  // Three GET refreshes per observed pending period; explicit refresh remains
  // available afterwards. Finite /events snapshots are not a live subscription.
  useEffect(() => {
    if (!pendingRun) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      if (session.getSnapshot().busy) return;
      attempts += 1;
      void session.refresh();
      if (attempts >= 3) window.clearInterval(timer);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [pendingRun, session]);
  const usable = docs.flatMap((doc) =>
    doc.versions
      .filter(
        ({ version }) =>
          version.status === "READY" && version.id === doc.active_version_id,
      )
      .map(({ version }) => ({ doc, version })),
  );
  const missing = state.versions.filter(
    (id) => !usable.some(({ version }) => version.id === id),
  );
  const disabled =
    state.busy ||
    !state.conversation ||
    !!state.pending ||
    !!state.conversation.active_run_id ||
    !state.versions.length ||
    !!missing.length;
  const send = async () => {
    if (disabled || !question.trim()) return;
    const submitted = question;
    onSelect(null);
    setFocusedRunId(null);
    setView("answer");
    await session.submit(submitted, {
      kb_id: kbId,
      version_ids: state.versions,
    });
    if (session.getSnapshot().pending || !session.getSnapshot().notice)
      setQuestion("");
  };
  return (
    <>
      <aside className="conversation-rail" aria-label="会话导航">
        <div className="section-heading">
          <h3>会话</h3>
          <span>{turnIds.length} 轮</span>
        </div>
        <div className="rail-heading">
          <span className="eyebrow">CONVERSATION</span>
          <h3>
            问题在延续，
            <br />
            证据每轮重查。
          </h3>
        </div>
        <nav aria-label="选择会话轮次" className="turn-navigation">
          {state.runs.map((run) => (
            <button
              key={run.id}
              className={
                focusedRun?.id === run.id ? "turn-link selected" : "turn-link"
              }
              aria-current={focusedRun?.id === run.id ? "step" : undefined}
              onClick={() => {
                setFocusedRunId(run.id);
                setView("answer");
                onSelect(null);
              }}
            >
              <span className="turn-number">
                {String(turnIds.indexOf(run.turn_id) + 1).padStart(2, "0")}
              </span>
              <span>
                <strong>
                  {state.traces[run.id]?.original_question ?? "正在读取问题…"}
                </strong>
                <small>
                  {run.status === "ACCEPTED"
                    ? "答案已发布"
                    : labels[run.status]}
                </small>
              </span>
            </button>
          ))}
          {!state.runs.length && (
            <p className="muted rail-empty">
              你的问题与每轮运行记录将保存在这里。
            </p>
          )}
        </nav>
        <div className="rail-sources">
          <span className="eyebrow">CURRENT SOURCES</span>
          <p>{state.versions.length} 个明确版本</p>
          <small>当前轮使用所选文档，引用绑定原始版本。</small>
        </div>
      </aside>
      <div className="chat-panel conversational-panel">
        <div className="section-heading">
          <h3>
            会话证据问答{" "}
            {focusedNumber > 0 && (
              <span className="turn-heading">/ 第 {focusedNumber} 轮</span>
            )}
          </h3>
          <span>
            {focusedRun?.status === "ACCEPTED"
              ? "已发布 · 可核查"
              : "服务端持久状态"}
          </span>
        </div>
        <div className="conversation-controls">
          {state.notice && (
            <p role="alert" className="warning-banner">
              {state.notice}
            </p>
          )}
          {!!missing.length && (
            <p role="alert" className="warning-banner">
              已选版本不在当前可用列表中，请重新选择：{missing.join(", ")}{" "}
              <button
                type="button"
                className="text-button"
                disabled={state.busy}
                onClick={() =>
                  session.setVersions(
                    state.versions.filter((id) => !missing.includes(id)),
                  )
                }
              >
                移除不可用选择
              </button>
            </p>
          )}
          <details
            className="conversation-settings"
            open={!state.conversation || undefined}
          >
            <summary>
              下一轮来源范围 · {state.versions.length} 个固定版本{" "}
              <span>调整文档 / 会话设置</span>
            </summary>
            <div className="conversation-settings-body">
              <div className="conversation-actions">
                {!state.conversation && (
                  <Button
                    disabled={state.busy}
                    onClick={() => void session.start()}
                  >
                    {state.hasIdentity ? "恢复会话身份" : "开始会话"}
                  </Button>
                )}
                {state.conversation && (
                  <Button
                    variant="outline"
                    disabled={
                      state.busy ||
                      !!state.pending ||
                      !!state.conversation.active_run_id
                    }
                    onClick={() => {
                      onSelect(null);
                      setQuestion("");
                      setFocusedRunId(null);
                      setView("answer");
                      void session.start(true);
                    }}
                  >
                    新会话
                  </Button>
                )}
                <Button
                  variant="outline"
                  disabled={state.busy || !state.hasIdentity}
                  onClick={() => void session.refresh()}
                >
                  刷新持久状态
                </Button>
                {state.pending && (
                  <Button
                    disabled={state.busy}
                    onClick={() => void session.recover()}
                  >
                    使用同一提交身份恢复
                  </Button>
                )}
              </div>
              <details className="source-details">
                <summary>打开已有会话</summary>
                <label>
                  Conversation ID
                  <input
                    value={existingConversation}
                    onChange={(e) => setExistingConversation(e.target.value)}
                    disabled={state.busy}
                  />
                </label>
                <label>
                  Run IDs（逗号或换行分隔）
                  <textarea
                    value={existingRuns}
                    onChange={(e) => setExistingRuns(e.target.value)}
                    disabled={state.busy}
                    rows={2}
                  />
                </label>
                <p className="version-meta">
                  读取指定运行的持久记录；不会创建会话或重新执行。最多 25
                  条，身份可从 Run 检查视图复制。
                </p>
                <Button
                  variant="outline"
                  disabled={
                    state.busy ||
                    !!state.pending ||
                    !existingConversation.trim() ||
                    !existingRuns.trim()
                  }
                  onClick={() => {
                    onSelect(null);
                    setFocusedRunId(null);
                    setView("answer");
                    void session.openExisting(
                      existingConversation,
                      existingRuns.split(/[,，\s]+/).filter(Boolean),
                    );
                  }}
                >
                  读取已有会话
                </Button>
              </details>
              {state.conversation && (
                <details className="source-details">
                  <summary>当前会话身份</summary>
                  <p className="version-meta">
                    Conversation {state.conversation.id}
                    <br />
                    已接受 head：{state.conversation.head_id ?? "无"}
                    <br />
                    活动 Run：{state.conversation.active_run_id ?? "无"}
                  </p>
                </details>
              )}
              <fieldset className="conversation-scope" disabled={state.busy}>
                <legend>下一轮文档范围 · {state.versions.length} 个版本</legend>
                {usable.map(({ doc, version }) => (
                  <label className="scope-option" key={version.id}>
                    <input
                      type="checkbox"
                      checked={state.versions.includes(version.id)}
                      onChange={(event) =>
                        session.setVersions(
                          event.target.checked
                            ? [...state.versions, version.id]
                            : state.versions.filter((id) => id !== version.id),
                        )
                      }
                    />
                    <span>
                      {doc.title} · v{version.sequence}
                      <small className="scope-version-id" title={version.id}>
                        READY · 固定版本
                      </small>
                    </span>
                  </label>
                ))}
                {!usable.length && <p>请添加文档并等待处理完成。</p>}
              </fieldset>
              <p role="status" className="conversation-readback">
                {state.busy
                  ? "正在提交 / 读取持久状态…"
                  : state.pending && !state.pending.runId
                    ? "提交结果未确认"
                    : pendingRun
                      ? "ADMITTED · 等待结果；有限自动读回后可手动刷新"
                      : state.conversation
                        ? "持久状态已读回"
                        : "尚未连接会话"}
              </p>
              {!state.conversation && (
                <small className="muted">
                  执行取决于服务器授权；已有结果可读取。
                </small>
              )}
            </div>
          </details>
        </div>
        {focusedRun && (
          <nav className="answer-tabs" aria-label="当前轮视图">
            <button
              aria-pressed={view === "answer"}
              onClick={() => setView("answer")}
            >
              回答与引用
            </button>
            <button
              aria-pressed={view === "trace"}
              onClick={() => setView("trace")}
            >
              运行过程{" "}
              <span>
                {focusedTrace?.operational?.total.latency_ms == null
                  ? ""
                  : `${(focusedTrace.operational.total.latency_ms / 1000).toFixed(2)} s`}
              </span>
            </button>
            <a
              className="context-view-link"
              href={`/runtime/context?run=${focusedRun.id}`}
            >
              上下文 / 指代解析 ↗
            </a>
          </nav>
        )}
        <div className="conversation" aria-label="会话记录">
          {!state.runs.length && !state.pending && (
            <p className="muted">
              选择明确的文档版本，开始会话后提问。刷新仅恢复此浏览器标签页已知的
              Run；当前 API 不提供完整历史列表。
            </p>
          )}
          {(focusedRun ? [focusedRun] : []).map((run) => (
            <article
              key={run.id}
              className="conversation-turn"
              aria-label={`Turn ${run.turn_id}`}
            >
              <div className="question-bubble">
                {state.traces[run.id]?.original_question ?? "原始问题暂不可用"}
              </div>
              <div className="answer-block">
                <div className="answer-author">
                  <span className="mini-logo">C</span>
                  <strong>CiteWeave</strong>
                  <span>
                    {run.status} · {labels[run.status]}
                  </span>
                </div>
                {view === "answer" ? (
                  <>
                    {focusedTrace && (
                      <ContextEvidenceSummary trace={focusedTrace} />
                    )}
                    <AcceptedAnswer
                      run={run}
                      selected={selected}
                      onSelect={onSelect}
                    />
                    <TraceInspector trace={state.traces[run.id]} />
                  </>
                ) : (
                  <div className="focused-trace">
                    {focusedTrace && (
                      <OperationalTimeline trace={focusedTrace} />
                    )}
                    <TraceInspector trace={focusedTrace} />
                  </div>
                )}
              </div>
            </article>
          ))}
          {state.pending && !state.pending.runId && (
            <div>
              <p className="question-bubble">{state.pending.body.question}</p>
              <p>提交待确认；恢复会保留原问题、head 和版本范围。</p>
            </div>
          )}
        </div>
        {view === "answer" && (
          <form
            className="composer"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <label htmlFor="conversation-question">下一条问题或澄清回复</label>
            <textarea
              id="conversation-question"
              rows={2}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              disabled={disabled}
              placeholder="输入关于所选文档的问题…"
            />
            <div className="composer-foot">
              <span>仅使用上方明确选择的版本</span>
              <Button type="submit" disabled={disabled || !question.trim()}>
                发送会话问题
              </Button>
            </div>
          </form>
        )}
      </div>
      {selected && (
        <aside className="evidence-panel" aria-label="会话原文证据">
          <div className="section-heading">
            <h3>原文证据 · {selected.label}</h3>
            <button className="text-button" onClick={() => onSelect(null)}>
              关闭证据
            </button>
          </div>
          <PdfEvidence
            key={`${selected.document_version_id}:${selected.evidence_id}:${selected.span.start_offset}:${selected.span.end_offset}`}
            citation={selected}
          />
        </aside>
      )}
    </>
  );
}
