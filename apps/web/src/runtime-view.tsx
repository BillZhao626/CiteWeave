import { useQuery } from "@tanstack/react-query";
import { api, unwrap, message } from "./api";
import type { components } from "./generated/api";
import { statusTone } from "./product-facts";

export function CaseRuntimeView({
  evaluationId,
  value: c,
}: {
  evaluationId: string;
  value: components["schemas"]["EvalCase"];
}) {
  const runtime = useQuery({
    queryKey: ["case-runtime", evaluationId, c.case_id],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/evaluations/{eval_id}/cases/{case_id}/runtime", {
          params: { path: { eval_id: evaluationId, case_id: c.case_id } },
        }),
      ),
    refetchInterval: ["PENDING", "QUEUED", "RUNNING", "RETRY_WAIT"].includes(
      c.status,
    )
      ? 4000
      : false,
  });
  return (
    <div className="case-runtime">
      <p className="muted">
        PostgreSQL 持久状态 · 执行 {c.execution_attempt}/{c.max_attempts} · 派发{" "}
        {c.dispatch_count}/30 · 连续派发失败 {c.dispatch_failures}/10 · 容量等待{" "}
        {c.admission_deferrals}/12
      </p>
      {c.status === "OUTCOME_UNKNOWN" && (
        <p className="warning-banner">
          OUTCOME_UNKNOWN · 上游结果未知，不代表成功。不会自动重发 answer /
          judge；费用预留仍保留。
        </p>
      )}
      <p className="muted">
        阶段 {c.phase ?? "未记录"} · 错误 {c.last_error_category ?? "—"} /{" "}
        {c.last_error_code ?? "—"} · Fence {c.fence}
      </p>
      <p className="muted">
        绝对截止 {c.absolute_deadline ?? "历史未记录"} · 活跃截止{" "}
        {c.active_deadline ?? "尚未派发"}
      </p>
      {runtime.error && <p role="alert">{message(runtime.error)}</p>}
      {runtime.data && (
        <>
          <p>
            重试状态：{runtime.data.retry_state} ·
            新请求仍须调度器重新检查，不是前端授权。
          </p>
          <div className="ops-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Provider phase</th>
                  <th>尝试</th>
                  <th>状态</th>
                  <th>结果</th>
                  <th>预留 / 已知估算</th>
                </tr>
              </thead>
              <tbody>
                {runtime.data.phases.map((p) => (
                  <tr key={p.id}>
                    <td>{p.phase}</td>
                    <td>{p.phase_attempt}/2</td>
                    <td>
                      <span className={`status ${statusTone(p.state)}`}>
                        {p.state}
                      </span>
                    </td>
                    <td>{p.outcome}</td>
                    <td>
                      ¥{p.reserved_yuan.toFixed(4)} /{" "}
                      {p.estimated_yuan == null
                        ? "未知"
                        : `¥${p.estimated_yuan.toFixed(4)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!runtime.data.phases.length && (
            <p className="muted">
              没有 ProviderPhase 记录；历史执行不补造记录。
            </p>
          )}
          <details className="ops-json">
            <summary>Celery 通知 / dispatch generation</summary>
            <pre>{JSON.stringify(runtime.data.dispatches, null, 2)}</pre>
          </details>
        </>
      )}
    </div>
  );
}
