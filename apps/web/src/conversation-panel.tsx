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
      <p className="verified-label">
        引用与原文片段一致 · 不代表语义支持已验证
      </p>
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
              <small className="block-id">
                版本 {citation.document_version_id}
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
export function TraceInspector({ trace }: { trace?: ConversationTrace }) {
  return (
    <details className="trace conversation-trace">
      <summary>Trace Inspector · 持久记录</summary>
      <p>
        CURRENT_PACK_PHYSICAL_ONLY ≠ semantic
        support。物理引用校验不证明语义支持。
      </p>
      {!trace ? (
        <p>未记录 / 不可用</p>
      ) : (
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
      )}
    </details>
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
  useEffect(() => {
    void session.refresh();
  }, [session]);
  useEffect(() => {
    if (!state.conversation && selected) onSelect(null);
  }, [state.conversation, selected, onSelect]);
  const pendingRun = state.runs.some((run) => run.status === "ADMITTED");
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
    await session.submit(submitted, {
      kb_id: kbId,
      version_ids: state.versions,
    });
    if (session.getSnapshot().pending || !session.getSnapshot().notice)
      setQuestion("");
  };
  return (
    <>
      <div className="chat-panel conversational-panel">
        <div className="section-heading">
          <h3>会话证据问答</h3>
          <span>服务端持久状态</span>
        </div>
        <div className="conversation-controls">
          <p className="muted">生产会话运行时尚未开放；已有会话结果可读回。</p>
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
            <legend>
              下一 Turn 的明确文档范围 · {state.versions.length} 个版本
            </legend>
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
                  <small className="block-id">{version.id}</small>
                </span>
              </label>
            ))}
            {!usable.length && <p>请从左侧添加文档并等待处理完成。</p>}
            {!!missing.length && (
              <p role="alert">
                已选版本不在当前可用列表中，请重新选择：{missing.join(", ")}{" "}
                <button
                  type="button"
                  className="text-button"
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
          </fieldset>
          {state.notice && (
            <p role="alert" className="warning-banner">
              {state.notice}
            </p>
          )}
          <p role="status">
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
        </div>
        <div className="conversation" aria-label="会话记录">
          {!state.runs.length && !state.pending && (
            <p className="muted">
              选择明确的文档版本，开始会话后提问。刷新仅恢复此浏览器标签页已知的
              Run；当前 API 不提供完整历史列表。
            </p>
          )}
          {state.runs.map((run) => (
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
                <AcceptedAnswer
                  run={run}
                  selected={selected}
                  onSelect={onSelect}
                />
                <TraceInspector trace={state.traces[run.id]} />
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
