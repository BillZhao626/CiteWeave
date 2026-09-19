import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api, listDocs, listKBs, unwrap, message, type Citation } from "./api";
import { PdfEvidence } from "./pdf-evidence";
import { shortId } from "./product-facts";

export function DocumentsPage() {
  const [params, setParams] = useSearchParams();
  const kb = params.get("kb") ?? "";
  const kbs = useQuery({ queryKey: ["kbs"], queryFn: listKBs });
  const docs = useQuery({
    queryKey: ["documents", kb],
    enabled: !!kb,
    queryFn: () => listDocs(kb),
  });
  return (
    <section className="ops-page">
      <p className="eyebrow">SOURCE EXPLORER</p>
      <h1>文档 / 结构</h1>
      <p className="muted ops-intro">
        从文档版本进入真实 Section / Clause、Parent 与 RetrievalChild。
      </p>
      <label>
        知识库{" "}
        <select
          aria-label="结构知识库"
          value={kb}
          onChange={(e) => setParams({ kb: e.target.value })}
        >
          <option value="">选择知识库</option>
          {kbs.data?.map((k) => (
            <option key={k.id} value={k.id}>
              {k.name}
            </option>
          ))}
        </select>
      </label>
      {docs.error && <p role="alert">{message(docs.error)}</p>}
      <div className="ops-list">
        {docs.data?.map((d) => {
          const v = d.versions.find(
            (v) => v.version.id === d.active_version_id,
          )?.version;
          return (
            <article className="ops-row" key={d.id}>
              <div>
                <strong>{d.title}</strong>
                <small className="block-id">
                  {v?.page_count ?? 0} 页 · Version {shortId(v?.id ?? "")} ·{" "}
                  {v?.status ?? "未发布"}
                </small>
              </div>
              {v && (
                <Link className="ops-link" to={`/versions/${v.id}/structure`}>
                  检查结构 →
                </Link>
              )}
              <Link className="ops-link" to={`/documents/${d.id}/versions`}>
                版本
              </Link>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function StructureView() {
  const { id = "" } = useParams();
  return <Structure key={id} id={id} />;
}
function Structure({ id }: { id: string }) {
  const [params, setParams] = useSearchParams(),
    [offset, setOffset] = useState(0),
    [spanOffset, setSpanOffset] = useState(0),
    [childOffset, setChildOffset] = useState(0),
    [selected, setSelected] = useState<Citation | null>(null);
  const node = params.get("node") ?? "",
    artifact = params.get("artifact") ?? undefined;
  const meta = useQuery({
    queryKey: ["structure", id, artifact],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/versions/{version_id}/structure", {
          params: {
            path: { version_id: id },
            query: { artifact_id: artifact },
          },
        }),
      ),
  });
  const nodes = useQuery({
    queryKey: ["nodes", id, artifact, offset],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/versions/{version_id}/structure/nodes", {
          params: {
            path: { version_id: id },
            query: { artifact_id: artifact, limit: 50, offset },
          },
        }),
      ),
  });
  const context = useQuery({
    queryKey: ["node", id, artifact, node, spanOffset],
    enabled: !!node,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/versions/{version_id}/structure/nodes/{node_id}", {
          params: {
            path: { version_id: id, node_id: node },
            query: { artifact_id: artifact, offset: spanOffset, limit: 40 },
          },
        }),
      ),
  });
  const children = useQuery({
    queryKey: ["children", id, artifact, node, childOffset],
    enabled: !!node,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/versions/{version_id}/structure/children", {
          params: {
            path: { version_id: id },
            query: {
              artifact_id: artifact,
              parent_id: node,
              limit: 25,
              offset: childOffset,
            },
          },
        }),
      ),
  });
  function choose(identity: string) {
    setParams({ ...Object.fromEntries(params), node: identity });
    setSpanOffset(0);
    setChildOffset(0);
    setSelected(null);
  }
  return (
    <section className="ops-page">
      <p className="eyebrow">IMMUTABLE DOCUMENT STRUCTURE</p>
      <h1>Section / Clause → Parent → Child</h1>
      <p className="muted ops-intro">
        检查冻结的文档结构与原文成员。这里只读，不重新解析或编辑文档。
      </p>
      <Link className="ops-link" to="/documents">
        ← 文档
      </Link>
      {(meta.error || nodes.error || context.error || children.error) && (
        <p className="error" role="alert">
          {message(
            meta.error || nodes.error || context.error || children.error,
          )}{" "}
          · 旧版本可能没有结构工件。
        </p>
      )}
      {meta.data && (
        <p className="ops-id">
          Version {id} · Artifact {meta.data.id} · {meta.data.state}
        </p>
      )}
      <div className="structure-columns">
        <aside className="ops-panel structure-tree">
          <h2>文档层级</h2>
          {nodes.data?.map((n) => (
            <button
              className={`tree-node ${n.id === node ? "selected" : ""}`}
              key={n.id}
              onClick={() => choose(n.id)}
              style={{
                paddingLeft:
                  12 +
                  (n.kind === "partition"
                    ? 24
                    : Math.max(0, (n.number?.split(".").length ?? 1) - 1) * 12),
              }}
            >
              <small>
                {n.kind}
                {n.is_parent ? " / Parent" : ""} · p.{n.page_start + 1}–
                {n.page_end + 1}
              </small>
              <span>
                {n.number} {n.title || "正文上下文"}
              </span>
            </button>
          ))}
          <div className="ops-pager">
            <button
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              上一页
            </button>
            <span>
              {offset + 1}–{offset + (nodes.data?.length ?? 0)}
            </span>
            <button
              disabled={(nodes.data?.length ?? 0) < 50}
              onClick={() => setOffset(offset + 50)}
            >
              下一页
            </button>
          </div>
        </aside>
        <div>
          {!node && (
            <div className="ops-panel">选择一个章节或 Parent 检查原文。</div>
          )}
          {context.data && (
            <>
              <section className="ops-panel">
                <p className="eyebrow">{context.data.node.kind}</p>
                <h2>
                  {context.data.node.number} {context.data.node.title}
                </h2>
                <nav className="breadcrumb">
                  {context.data.ancestors.map((a) => (
                    <button
                      key={a.id}
                      className="text-button"
                      onClick={() => choose(a.id)}
                    >
                      {a.number} {a.title} ›
                    </button>
                  ))}
                </nav>
                <p className="ops-id">{node}</p>
                <p className="muted">
                  Confidence {context.data.node.confidence} ·{" "}
                  {context.data.node.reasons.join(", ") || "无降级原因"}
                </p>
                <h3>Parent / 节点原文上下文</h3>
                <p className="muted">
                  {context.data.total_spans} 个原始
                  EvidenceSpan；源文检查不代表已被某个答案引用。
                </p>
                <div className="source-context">
                  {context.data.spans.map((s) => (
                    <button
                      className="span-quote"
                      key={s.evidence_id}
                      onClick={() => setSelected(s)}
                    >
                      <small>
                        EvidenceSpan {shortId(s.evidence_id)} · p.
                        {s.span.boxes[0].page_index + 1}
                      </small>
                      <p>{s.span.quote}</p>
                    </button>
                  ))}
                </div>
                <div className="ops-pager">
                  <button
                    disabled={!spanOffset}
                    onClick={() => setSpanOffset(Math.max(0, spanOffset - 40))}
                  >
                    前 40 个原文片段
                  </button>
                  <button
                    disabled={spanOffset + 40 >= context.data.total_spans}
                    onClick={() => setSpanOffset(spanOffset + 40)}
                  >
                    后 40 个原文片段
                  </button>
                </div>
              </section>
              <section className="ops-panel">
                <h2>RetrievalChild / 原文成员</h2>
                <p className="muted">
                  选中 Parent 后显示其 Child；Child 用于检索，引用仍使用
                  EvidenceSpan。
                </p>
                {children.data?.map((c) => (
                  <details className="child-detail" key={c.id}>
                    <summary>
                      Child {shortId(c.id)} · {c.span_ids?.length} spans
                    </summary>
                    <p className="answer-text">{c.retrieval_text}</p>
                    <div className="member-ids">
                      {c.span_ids?.map((identity) => (
                        <code key={identity}>{identity}</code>
                      ))}
                    </div>
                  </details>
                ))}
                <div className="ops-pager">
                  <button
                    disabled={!childOffset}
                    onClick={() =>
                      setChildOffset(Math.max(0, childOffset - 25))
                    }
                  >
                    前 25 个 Child
                  </button>
                  <button
                    disabled={(children.data?.length ?? 0) < 25}
                    onClick={() => setChildOffset(childOffset + 25)}
                  >
                    后 25 个 Child
                  </button>
                </div>
              </section>
            </>
          )}
          {selected && (
            <section className="ops-panel">
              <h2>原文成员 → PDF</h2>
              <PdfEvidence key={selected.evidence_id} citation={selected} />
            </section>
          )}
        </div>
      </div>
    </section>
  );
}
