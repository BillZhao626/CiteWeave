import type { ConversationTrace } from "./conversation-session";

const phaseLabels: Record<string, string> = {
  interpretation: "处理解释结果",
  history: "选择相关上下文",
  admission_queue: "请求准入与排队",
  retrieval: "检索当前证据",
  generation: "依据证据生成",
  validation: "校验引用",
  publication: "一致发布",
  admission: "请求准入",
  scope: "检查文档范围",
};

export function RunOverview({ trace }: { trace?: ConversationTrace }) {
  if (!trace?.operational) return null;
  const { operational } = trace;
  const stages = operational.timeline.filter(
    (item) =>
      (item.kind === "stage_completed" && item.phase !== "interpretation") ||
      (item.kind === "provider_completed" && item.phase === "interpretation"),
  );
  const largest = Math.max(1, ...stages.map((item) => item.latency_ms ?? 0));
  const generationAt = operational.timeline.findIndex(
    (item) => item.kind === "stage_started" && item.phase === "generation",
  );
  return (
    <div className="run-overview" aria-label="已记录执行阶段">
      <div className="run-outcome">
        <span
          className={
            operational.publication === "ACCEPTED"
              ? "run-published"
              : "run-unpublished"
          }
        >
          {operational.publication === "ACCEPTED"
            ? "答案与会话状态已发布"
            : "本次结果未发布"}
        </span>
        <small title={trace.run_id}>Run {trace.run_id.slice(0, 8)}</small>
      </div>
      <div className="run-identity-strip">
        <span title={trace.conversation_id}>
          Conversation {trace.conversation_id.slice(0, 8)}
        </span>
        <span title={trace.turn_id}>Turn {trace.turn_id.slice(0, 8)}</span>
        <span>
          总耗时{" "}
          {operational.total.latency_ms == null
            ? "未记录"
            : `${(operational.total.latency_ms / 1000).toFixed(2)} s`}
        </span>
      </div>
      <ol className="run-stage-list">
        {stages.map((item) => (
          <li key={item.id}>
            <span className="stage-dot" />
            <div>
              <strong>
                {item.phase === "validation" && generationAt >= 0
                  ? operational.timeline.findIndex(
                      (event) => event.id === item.id,
                    ) < generationAt
                    ? "核验当前证据"
                    : "校验答案引用"
                  : item.kind === "provider_completed"
                    ? "模型理解当前问题"
                    : (phaseLabels[item.phase ?? ""] ??
                      item.phase ??
                      "未记录阶段")}
              </strong>
              <span className="stage-duration">
                {item.latency_ms == null
                  ? "耗时未记录"
                  : `${item.latency_ms.toLocaleString()} ms`}
              </span>
              <div className="stage-bar-track">
                {item.latency_ms != null && (
                  <span
                    style={{ width: `${(item.latency_ms / largest) * 100}%` }}
                  />
                )}
              </div>
              <small>{item.to_state ?? "已记录"}</small>
            </div>
          </li>
        ))}
      </ol>
      {stages.length === 0 && <p className="muted">阶段耗时未记录</p>}
      <div className="run-usage">
        {operational.provider_phases.map((phase) => (
          <span key={phase.provider_phase_id}>
            {phaseLabels[phase.phase] ?? phase.phase} · 第{" "}
            {phase.attempt ?? "未记录"} 次 · {phase.state}
            {phase.usage?.total_tokens != null &&
              ` · ${phase.usage.total_tokens} tokens`}
            {phase.estimated_yuan != null && ` · 估算 ¥${phase.estimated_yuan}`}
          </span>
        ))}
      </div>
    </div>
  );
}
