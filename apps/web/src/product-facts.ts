import type { components } from "./generated/api";

export type Run = components["schemas"]["Run"];
export const shortId = (value: string) => value.slice(0, 12);
export function statusTone(value: string) {
  if (["COMPLETED", "READY", "closed"].includes(value)) return "ready";
  if (
    ["FAILED", "FAILED_FINAL", "OUTCOME_UNKNOWN", "UNKNOWN", "open"].includes(
      value,
    )
  )
    return "failed";
  if (value === "CANCELLED") return "cancelled";
  return "pending";
}
export function sectionPath(path: Record<string, unknown>[]) {
  return (
    path
      .map((part) => [part.number, part.title].filter(Boolean).join(" "))
      .join(" › ") || "未记录章节"
  );
}
export function candidateRanks(
  candidate: components["schemas"]["StructuralCandidate"],
  degraded: boolean,
) {
  return {
    dense:
      candidate.retrieval.find((hit) => hit.branch === "dense")?.rank ?? null,
    bm25:
      candidate.retrieval.find((hit) => hit.branch === "bm25")?.rank ?? null,
    rrf: candidate.rrf_rank,
    bge: degraded ? null : (candidate.bge?.output_rank ?? null),
    score: degraded ? null : (candidate.bge?.score ?? null),
  };
}
export function generationLabel(run: Run) {
  const ids = [
    ...run.calls.map((call) => String(call.provider_id ?? "")),
    String(run.usage?.provider_id ?? ""),
    String(run.result?.usage?.provider_id ?? ""),
  ];
  if (ids.some((id) => /mock|fixture/i.test(id)))
    return "MOCK · 工程回放 · 非答案质量证据";
  if (run.result && !run.calls.some((call) => call.upstream === "deepseek"))
    return "生成来源未记录 / 无外部生成调用 · 不作质量声明";
  return "生成调用见运行记录 · 不代表质量评测通过";
}
export function judgmentLabel(judge: Record<string, unknown>) {
  return judge.status === "COMPLETED" &&
    judge.scores &&
    typeof judge.scores === "object"
    ? "语义判断可用 · Judge 辅助判断"
    : "缺少语义判断 · 不是 0 分";
}
