import { useState } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api, unwrap, message, type Citation } from "./api";
import { PdfEvidence } from "./pdf-evidence";
import {
  candidateRanks,
  generationLabel,
  sectionPath,
  shortId,
  type Run,
} from "./product-facts";

export function StructuralTrace({ run }: { run: Run }) {
  const [selected, setSelected] = useState<Citation | null>(null);
  const evidence = useQuery({
    queryKey: ["trace-citation", run.id, selected?.evidence_id],
    enabled: !!selected,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/evidence/{evidence_id}", {
          params: {
            path: { evidence_id: selected!.evidence_id },
            query: { run_id: run.id },
          },
        }),
      ),
  });
  const pack = run.evidence_pack;
  const bindings = run.structural_snapshot?.bindings ?? [];
  const source = (documentId: string) =>
    bindings.find((b) => b.document_id === documentId)?.filename ??
    shortId(documentId);
  return (
    <div data-testid="structural-trace">
      <p className="ops-notice">{generationLabel(run)}</p>
      {pack?.degraded && (
        <p role="status" className="warning-banner">
          降级检索 · {pack.degraded} · 本次 BGE 不可用；使用 RRF 种子，不展示
          BGE 分数。
        </p>
      )}
      {pack?.source_coverage.coverage_unmet && (
        <p className="warning-banner" data-testid="source-gaps">
          来源缺口 · {pack.source_coverage.missing.map(source).join("、")}
          。这些来源未进入最终上下文。
        </p>
      )}
      <section className="ops-panel">
        <h2>固定来源与构建</h2>
        <p className="muted">
          QueryRun → Source / Version / Build；所有身份来自此运行的冻结快照。
        </p>
        <div className="ops-table-wrap">
          <table>
            <thead>
              <tr>
                <th>来源</th>
                <th>Version</th>
                <th>Artifact / Build</th>
                <th>源字节 SHA</th>
              </tr>
            </thead>
            <tbody>
              {bindings.map((b) => (
                <tr key={b.version_id}>
                  <td>
                    <Link
                      className="ops-link"
                      to={`/versions/${b.version_id}/structure?artifact=${b.artifact_id}`}
                    >
                      {b.filename}
                    </Link>
                  </td>
                  <td title={b.version_id}>{shortId(b.version_id)}</td>
                  <td>
                    <span title={b.artifact_id}>{shortId(b.artifact_id)}</span>
                    <small className="block-id">{b.index_name}</small>
                  </td>
                  <td title={b.source_sha256}>{shortId(b.source_sha256)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="ops-panel" data-testid="candidate-table">
        <h2>RetrievalChild · 检索候选与种子</h2>
        <p className="muted">
          Dense / BM25 排名按对应构建解释；RRF 与 BGE 是候选排名。Child ID 不是
          Citation ID。
        </p>
        <div className="ops-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Child / 章节 / Parent</th>
                <th>来源</th>
                <th>Dense</th>
                <th>BM25</th>
                <th>RRF</th>
                <th>BGE</th>
                <th>种子决策</th>
              </tr>
            </thead>
            <tbody>
              {run.structural_candidates?.map((c) => {
                const ranks = candidateRanks(c, !!pack?.degraded);
                return (
                  <tr key={c.child_id} data-seed={c.seed_rank != null}>
                    <td>
                      <code title={c.child_id}>{shortId(c.child_id)}</code>
                      <p>{sectionPath(c.section_path)}</p>
                      <Link
                        className="ops-link"
                        to={`/versions/${c.version_id}/structure?artifact=${c.artifact_id}&node=${c.parent_id}`}
                      >
                        Parent {shortId(c.parent_id)} →
                      </Link>
                    </td>
                    <td>{source(c.document_id)}</td>
                    <td>{ranks.dense ?? "—"}</td>
                    <td>{ranks.bm25 ?? "—"}</td>
                    <td>
                      {ranks.rrf}
                      <small className="block-id">
                        {c.rrf_score.toFixed(5)}
                      </small>
                    </td>
                    <td>
                      {ranks.bge ?? "—"}
                      <small className="block-id">
                        {ranks.score?.toFixed(4) ?? "未运行 / 不在重排池"}
                      </small>
                    </td>
                    <td>
                      {c.seed_rank ? `Seed ${c.seed_rank}` : "未选为种子"}
                      <small className="block-id">{c.selection_reason}</small>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      {pack && (
        <section className="ops-panel" data-testid="evidence-pack">
          <h2>Parent-aware EvidencePack</h2>
          <p className="muted">
            原始 EvidenceSpan 与检索 Child 分开。heading / sibling 是 Parent
            追加证据，没有独立检索排名。
          </p>
          <div className="ops-metrics">
            {[
              ["种子 Child", pack.seed_child_ids.length],
              ["种子字符", pack.seed_chars],
              ["Parent 追加字符", pack.added_chars],
              ["最终原文片段", pack.spans.length],
              ["序列化字符", pack.serialized_chars],
              ["BGE token proxy", pack.serialized_tokens],
            ].map(([label, value]) => (
              <div className="ops-metric" key={label}>
                <small>{label}</small>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <p className="muted">
            模式 {pack.evidence_mode} · Token proxy 不是生成模型的 token 计数。
          </p>
          <div className="ops-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>EvidenceSpan / 标签</th>
                  <th>来源</th>
                  <th>证据来源</th>
                  <th>Parent / Seed Child</th>
                  <th>最终 Citation</th>
                </tr>
              </thead>
              <tbody>
                {pack.spans.map((s) => {
                  const citation = run.result?.citations.find(
                    (c) => c.evidence_id === s.evidence_id,
                  );
                  return (
                    <tr key={s.evidence_id} data-origin={s.origin}>
                      <td>
                        {s.label}
                        <small className="block-id" title={s.evidence_id}>
                          {shortId(s.evidence_id)}
                        </small>
                      </td>
                      <td>{source(s.document_id)}</td>
                      <td>
                        {s.origin}
                        {s.cross_page ? " · 跨页" : ""}
                      </td>
                      <td>
                        <span title={s.parent_id}>{shortId(s.parent_id)}</span>
                        <small className="block-id" title={s.seed_child_id}>
                          {shortId(s.seed_child_id)}
                        </small>
                      </td>
                      <td>
                        {citation ? (
                          <button
                            className="text-button"
                            onClick={() => setSelected(citation)}
                          >
                            查看引用 {citation.label}
                          </button>
                        ) : (
                          "未被最终答案引用"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <details className="ops-json">
            <summary>Parent 预算与选择决策</summary>
            <pre>{JSON.stringify(pack.decisions, null, 2)}</pre>
          </details>
        </section>
      )}
      {selected && (
        <section className="ops-panel trace-pdf">
          <div className="ops-heading">
            <h2>最终 Citation → 原始 PDF</h2>
            <button className="text-button" onClick={() => setSelected(null)}>
              关闭证据
            </button>
          </div>
          {evidence.error && <p role="alert">{message(evidence.error)}</p>}
          {evidence.data && (
            <PdfEvidence
              key={evidence.data.evidence_id}
              citation={evidence.data}
            />
          )}
        </section>
      )}
    </div>
  );
}
