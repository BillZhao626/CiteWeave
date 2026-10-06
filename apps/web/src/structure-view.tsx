import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api, listDocs, listKBs, unwrap, message, type Citation } from "./api";
import { PdfEvidence } from "./pdf-evidence";
import { shortId, statusTone } from "./product-facts";
import type { Doc } from "./api";
import { FileText, Search, ArrowUpRight, Layers } from "lucide-react";

export function DocumentsPage() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const kb = params.get("kb") ?? "";
  const kbs = useQuery({ queryKey: ["kbs"], queryFn: listKBs });
  const docs = useQuery({
    queryKey: ["documents", kb],
    enabled: !!kb,
    queryFn: () => listDocs(kb),
    refetchInterval: 5000,
  });
  const visible =
    docs.data?.filter((d) =>
      `${d.title} ${d.versions.map((v) => v.version.filename).join(" ")}`
        .toLocaleLowerCase()
        .includes(search.toLocaleLowerCase()),
    ) ?? [];
  const selected =
    visible.find((d) => d.id === params.get("document")) ?? visible[0];
  const ready =
    docs.data?.filter((d) =>
      d.versions.some(
        (v) =>
          v.version.id === d.active_version_id && v.version.status === "READY",
      ),
    ).length ?? 0;
  return (
    <section className="ops-page source-explorer">
      <p className="eyebrow">SOURCE EXPLORER</p>
      <h1>文档与版本</h1>
      <p className="muted ops-intro">
        从已发布的来源出发，检查不可变版本、章节结构与原始证据。
      </p>
      <div className="source-toolbar">
        <label>
          知识库
          <select
            aria-label="结构知识库"
            value={kb}
            onChange={(e) => {
              setParams({ kb: e.target.value });
              setSearch("");
            }}
          >
            <option value="">选择知识库</option>
            {kbs.data?.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </select>
        </label>
        <label className="source-search">
          <Search size={15} />
          <input
            aria-label="搜索来源文档"
            placeholder="搜索文档或文件名"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        {docs.data && (
          <span className="source-count">
            {ready} 个可用来源 / {docs.data.length} 份文档
          </span>
        )}
      </div>
      {(docs.error || kbs.error) && (
        <p role="alert" className="error">
          {message(docs.error || kbs.error)}
        </p>
      )}
      {!kb && (
        <div className="source-empty">
          <Layers size={28} />
          <h2>选择一个知识库</h2>
          <p>查看其中的来源、版本与可追溯证据。</p>
        </div>
      )}
      {docs.isFetching && !docs.data && kb && (
        <p className="muted">正在读取来源…</p>
      )}
      {docs.data && (
        <div className="source-split">
          <div className="source-library">
            <div className="source-library-heading">
              <h2>来源文档</h2>
              <span>{visible.length} 份</span>
            </div>
            <div className="ops-table-wrap source-table">
              <table>
                <thead>
                  <tr>
                    <th>文档 / 原始文件</th>
                    <th>当前版本</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((d) => {
                    const current = d.versions.find(
                      (v) => v.version.id === d.active_version_id,
                    )?.version;
                    const latest = [...d.versions].sort(
                      (a, b) => b.version.sequence - a.version.sequence,
                    )[0]?.version;
                    return (
                      <tr key={d.id} data-selected={d.id === selected?.id}>
                        <td>
                          <button
                            className="source-select"
                            aria-pressed={d.id === selected?.id}
                            onClick={() => setParams({ kb, document: d.id })}
                          >
                            <FileText size={18} />
                            <span>
                              <strong>{d.title}</strong>
                              <small>
                                {current?.filename ??
                                  latest?.filename ??
                                  "没有上传版本"}
                              </small>
                            </span>
                          </button>
                        </td>
                        <td>
                          {current ? (
                            <>
                              <strong>v{current.sequence}</strong>
                              <small>{current.page_count} 页</small>
                            </>
                          ) : (
                            "未发布"
                          )}
                        </td>
                        <td>
                          <span
                            className={`status ${statusTone(current?.status ?? latest?.status ?? "PENDING")}`}
                          >
                            {current?.status ?? latest?.status ?? "未发布"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {!visible.length && (
              <p className="source-empty">
                {search ? "没有匹配的文档。" : "这个知识库还没有文档。"}
              </p>
            )}
            {selected && <SourceIngestionPreview document={selected} />}
          </div>
          {selected && <SourceDetails key={selected.id} document={selected} />}
        </div>
      )}
    </section>
  );
}

function SourceIngestionPreview({ document: d }: { document: Doc }) {
  const upload =
    d.versions.find((v) => v.version.id === d.active_version_id) ??
    [...d.versions].sort((a, b) => b.version.sequence - a.version.sequence)[0];
  if (!upload) return null;
  const job = upload.job;
  const names: Record<string, string> = {
    PARSING: "解析原文",
    CHUNKING: "构建片段",
    EMBEDDING: "生成向量",
    INDEXING: "写入索引",
    READY: "版本发布",
    RETRY_WAIT: "等待重试",
    FAILED_FINAL: "任务终止",
  };
  return (
    <div className="source-job-preview">
      <div className="source-library-heading">
        <h3>所选来源的入库记录</h3>
        <Link className="text-button" to={`/system?job=${job.id}`}>
          查看任务 ↗
        </Link>
      </div>
      <div className="source-job-summary">
        <span>{upload.version.filename}</span>
        <span>
          尝试 {job.attempt}/{job.max_attempts}
        </span>
        <span className={`status ${statusTone(job.status)}`}>{job.status}</span>
      </div>
      {job.events.length ? (
        <ol aria-label="来源入库事件">
          {job.events.map((e, i) => (
            <li key={i} data-status={String(e.status ?? "")}>
              <span className="source-job-dot" />
              <strong>
                {names[String(e.status)] ?? String(e.status ?? "未记录")}
              </strong>
              <small>
                {typeof e.at === "string" && !Number.isNaN(Date.parse(e.at))
                  ? new Date(e.at).toLocaleTimeString("zh-CN", {
                      hour12: false,
                    })
                  : "未记录时间"}
              </small>
              <code>{String(e.status ?? "未记录")}</code>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">未记录任务事件。</p>
      )}
      <div className="source-job-publication">
        {job.status === "READY"
          ? d.active_version_id === upload.version.id &&
            upload.version.status === "READY"
            ? "READY 已持久提交 · 当前版本可用于检索"
            : "READY 已持久提交 · 此次版本处理完成"
          : `当前任务状态 · ${job.status}`}
        <small title={job.id}>Job {shortId(job.id)}</small>
      </div>
    </div>
  );
}

function SourceDetails({ document: d }: { document: Doc }) {
  const current = d.versions.find((v) => v.version.id === d.active_version_id);
  const uploaded =
    current ??
    [...d.versions].sort((a, b) => b.version.sequence - a.version.sequence)[0];
  const v = uploaded?.version;
  const structure = useQuery({
    queryKey: ["source-sections", v?.id],
    enabled: v?.status === "READY",
    retry: false,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/versions/{version_id}/structure/nodes", {
          params: {
            path: { version_id: v!.id },
            query: { limit: 100, offset: 0 },
          },
        }),
      ),
  });
  return (
    <aside className="source-detail">
      <p className="eyebrow">
        {current ? "PUBLISHED SOURCE" : "LATEST UPLOAD"}
      </p>
      <h2>{d.title}</h2>
      {v && (
        <>
          <div className="source-publication">
            <span className={`status ${statusTone(v.status)}`}>{v.status}</span>
            <span>
              v{v.sequence} · {current ? "当前发布版本" : "尚未发布"}
            </span>
          </div>
          <p className="source-publication-copy">
            {current && v.status === "READY"
              ? "新问题可检索此版本；已完成答案保留原来的来源身份。"
              : "处理状态来自持久记录；发布后才进入新问题的检索范围。"}
          </p>
          <dl className="source-facts">
            <div>
              <dt>原始文件</dt>
              <dd>{v.filename}</dd>
            </div>
            <div>
              <dt>原文结构</dt>
              <dd>
                {v.page_count} 页 · {v.chunk_count} 个片段
              </dd>
            </div>
            <div>
              <dt>来源许可</dt>
              <dd>{v.license || "未记录"}</dd>
            </div>
            <div>
              <dt>登记时间</dt>
              <dd>
                {new Date(v.created_at).toLocaleString("zh-CN", {
                  hour12: false,
                })}
              </dd>
            </div>
            <div>
              <dt>不可变版本</dt>
              <dd>
                <code title={v.id}>{shortId(v.id)}</code>
              </dd>
            </div>
            <div>
              <dt>原件 SHA-256</dt>
              <dd>
                <code title={v.source_sha256}>{shortId(v.source_sha256)}</code>
              </dd>
            </div>
            <div>
              <dt>派生索引</dt>
              <dd className="source-index">
                {v.index_collection ?? "尚未发布"}
              </dd>
            </div>
          </dl>
          {!!structure.data?.filter((n) => n.title || n.number).length && (
            <div className="source-sections">
              <h3>已解析章节</h3>
              {structure.data
                .filter((n) => n.title || n.number)
                .slice(0, 4)
                .map((n) => (
                  <Link
                    key={n.id}
                    to={`/versions/${v.id}/structure?node=${n.id}`}
                  >
                    <span>
                      {n.number} {n.title || "正文上下文"}
                    </span>
                    <small>
                      p.{n.page_start + 1}–{n.page_end + 1}
                    </small>
                  </Link>
                ))}
            </div>
          )}
          {structure.error && (
            <p className="muted source-structure-note">
              此版本的结构暂不可读取，可进入版本页查看来源记录。
            </p>
          )}
          <div className="source-detail-actions">
            <Link to={`/documents/${d.id}/versions`}>
              查看 {d.versions.length} 个版本 <ArrowUpRight size={15} />
            </Link>
            {v.status === "READY" && (
              <Link to={`/versions/${v.id}/structure`}>
                打开原文结构 <ArrowUpRight size={15} />
              </Link>
            )}
            <Link to={`/system?job=${uploaded.job.id}`}>
              查看入库任务 <ArrowUpRight size={15} />
            </Link>
          </div>
          <details className="source-details">
            <summary>完整来源与版本身份</summary>
            <p className="ops-id">Document {d.id}</p>
            <p className="ops-id">Version {v.id}</p>
            <p className="ops-id">SHA-256 {v.source_sha256}</p>
          </details>
        </>
      )}
    </aside>
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
      <h1>文档结构 / Section & Clause</h1>
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
        <details className="source-details">
          <summary>结构工件 · {meta.data.state} · 版本与身份</summary>
          <p className="ops-id">
            Version {id} · Artifact {meta.data.id} · {meta.data.state}
          </p>
        </details>
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
                <details className="source-details">
                  <summary>解析与节点详情</summary>
                  <p className="ops-id">{node}</p>
                  <p className="muted">
                    结构解析 Confidence {context.data.node.confidence} ·{" "}
                    {context.data.node.reasons.join(", ") || "无降级原因"}
                  </p>
                </details>
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
