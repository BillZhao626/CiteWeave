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
  const [showAll, setShowAll] = useState(false);
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
  const candidates = run.structural_candidates ?? [];
  const visible = showAll
    ? candidates
    : candidates
        .filter((c) => c.seed_rank != null)
        .sort((a, b) => a.seed_rank! - b.seed_rank!);
  const branchCount = (branch: string) =>
    candidates.filter((c) => c.retrieval.some((h) => h.branch === branch))
      .length;
  return (
    <div data-testid="structural-trace" className="retrieval-inspector">
      <div className="retrieval-overview">
        <p className="eyebrow">RETRIEVAL INSPECTOR</p>
        <h2>从检索候选，到当前答案的证据</h2>
        <div className="inspector-flow" aria-label="实际检索阶段">
          <div>
            <small>01 / 并行召回</small>
            <strong>Dense + BM25</strong>
            <span>
              {branchCount("dense")} / {branchCount("bm25")} 个候选
            </span>
          </div>
          <div>
            <small>02 / 排名融合</small>
            <strong>RRF</strong>
            <span>{candidates.length} 个合并候选</span>
          </div>
          <div>
            <small>03 / 相关性重排</small>
            <strong>BGE</strong>
            <span>
              {pack?.degraded
                ? "不可用 · 使用 RRF"
                : `${candidates.filter((c) => c.bge).length} 个已重排候选`}
            </span>
          </div>
          <div>
            <small>04 / 原文上下文</small>
            <strong>Evidence</strong>
            <span>{pack?.spans.length ?? "—"} 个原文片段</span>
          </div>
          <div>
            <small>05 / 答案引用</small>
            <strong>Citation</strong>
            <span>{run.result?.citations.length ?? 0} 条最终引用</span>
          </div>
        </div>
        <div className="retrieval-source-bindings">
          {bindings.map((b) => (
            <Link
              key={b.version_id}
              to={`/versions/${b.version_id}/structure?artifact=${b.artifact_id}`}
            >
              <span>{b.filename}</span>
              <span>固定来源 ↗</span>
            </Link>
          ))}
        </div>
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
        <details className="ops-json">
          <summary>固定来源与构建身份</summary>
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
                      <span title={b.artifact_id}>
                        {shortId(b.artifact_id)}
                      </span>
                      <small className="block-id">{b.index_name}</small>
                    </td>
                    <td title={b.source_sha256}>{shortId(b.source_sha256)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
        <section className="retrieval-panel" data-testid="candidate-table">
          <div className="ops-heading">
            <h2>{showAll ? "全部检索候选" : "进入证据上下文的候选"}</h2>
            <button
              className="text-button"
              aria-pressed={showAll}
              onClick={() => setShowAll(!showAll)}
            >
              {showAll
                ? "只看已选候选"
                : `查看全部 ${candidates.length} 个候选`}
            </button>
          </div>
          <p className="muted">
            Dense / BM25 排名按对应构建解释；RRF 与 BGE 是候选排名。Child ID
            不是 Citation ID。
          </p>
          <div className="ops-table-wrap retrieval-table">
            <table>
              <thead>
                <tr>
                  <th>章节与原文成员</th>
                  <th>来源</th>
                  <th>Dense</th>
                  <th>BM25</th>
                  <th>RRF</th>
                  <th>BGE</th>
                  <th>选入证据</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((c) => {
                  const ranks = candidateRanks(c, !!pack?.degraded);
                  return (
                    <tr key={c.child_id} data-seed={c.seed_rank != null}>
                      <td className="retrieval-candidate">
                        <p>{sectionPath(c.section_path)}</p>
                        <code title={c.child_id}>
                          Child {shortId(c.child_id)}
                        </code>
                        <Link
                          className="ops-link"
                          to={`/versions/${c.version_id}/structure?artifact=${c.artifact_id}&node=${c.parent_id}`}
                        >
                          检查 Parent 原文 →
                        </Link>
                      </td>
                      <td>{source(c.document_id)}</td>
                      <td className="retrieval-rank">
                        {ranks.dense != null ? `#${ranks.dense}` : "—"}
                        <small>
                          {c.retrieval
                            .find((h) => h.branch === "dense")
                            ?.raw_score.toFixed(4) ?? "未召回"}
                        </small>
                      </td>
                      <td className="retrieval-rank">
                        {ranks.bm25 != null ? `#${ranks.bm25}` : "—"}
                        <small>
                          {c.retrieval
                            .find((h) => h.branch === "bm25")
                            ?.raw_score.toFixed(3) ?? "未召回"}
                        </small>
                      </td>
                      <td className="retrieval-rank">
                        #{ranks.rrf}
                        <small className="block-id">
                          {c.rrf_score.toFixed(5)}
                        </small>
                      </td>
                      <td className="retrieval-rank">
                        {ranks.bge != null ? `#${ranks.bge}` : "—"}
                        <small className="block-id">
                          {ranks.score?.toFixed(4) ?? "未运行 / 不在重排池"}
                        </small>
                      </td>
                      <td>
                        {c.seed_rank ? (
                          <span className="retrieval-seed">
                            Seed {c.seed_rank}
                          </span>
                        ) : (
                          "未选为种子"
                        )}
                        <small className="block-id">{c.selection_reason}</small>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      {pack && (
        <section className="retrieval-panel" data-testid="evidence-pack">
          <h2>最终原文证据 / EvidencePack</h2>
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
                        <span className="evidence-label">{s.label}</span>
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
      <details className="ops-json">
        <summary>生成调用来源</summary>
        <p>{generationLabel(run)}</p>
      </details>
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
