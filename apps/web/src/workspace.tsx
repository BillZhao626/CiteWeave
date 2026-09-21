import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  Check,
  FileText,
  LoaderCircle,
  Upload,
  Search,
  X,
  Quote,
} from "lucide-react";
import { Button } from "./components/ui/button";
import {
  api,
  listDocs,
  message,
  unwrap,
  type Answer,
  type Citation,
  type Doc,
} from "./api";
import { readAnswer } from "./stream";
import { generationLabel, sectionPath } from "./product-facts";
import { PdfEvidence } from "./pdf-evidence";
import { citationForPart, citationParts } from "./citation-tokens";

const statuses: Record<string, string> = {
  PENDING: "已排队",
  PARSING: "解析原文",
  CHUNKING: "定位片段",
  EMBEDDING: "向量编码",
  INDEXING: "建立索引",
  RETRY_WAIT: "等待自动重试",
  READY: "可提问",
  FAILED_FINAL: "处理失败",
};

export function KnowledgeWorkspace() {
  const { id = "" } = useParams();
  return <Workspace key={id} id={id} />;
}

function Workspace({ id }: { id: string }) {
  const [params] = useSearchParams();
  const replayId = params.get("run") ?? "";
  const replay = useQuery({
    queryKey: ["run", replayId],
    enabled: !!replayId,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/runs/{run_id}", {
          params: { path: { run_id: replayId } },
        }),
      ),
  });
  const [profile, setProfile] = useState<
    "m3-context" | "telecom-structural-v1"
  >("m3-context");
  const [scope, setScope] = useState<string[]>([]);
  const [mode, setMode] = useState<"auto" | "single" | "compare">("auto");
  const cache = useQueryClient(),
    fileInput = useRef<HTMLInputElement>(null);
  const kb = useQuery({
    queryKey: ["kb", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/knowledge-bases/{kb_id}", {
          params: { path: { kb_id: id } },
        }),
      ),
  });
  const docs = useQuery({
    queryKey: ["documents", id],
    queryFn: () => listDocs(id),
    refetchInterval: (query) =>
      query.state.data?.some((d) =>
        d.versions.some(
          (v) => !["READY", "FAILED_FINAL"].includes(v.job.status),
        ),
      )
        ? 1500
        : false,
  });
  const [license, setLicense] = useState("original"),
    [replacing, setReplacing] = useState<string | null>(null);
  const [question, setQuestion] = useState(""),
    [draft, setDraft] = useState(""),
    [liveAnswer, setAnswer] = useState<Answer | null>(null);
  const [stage, setStage] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [liveRunId, setRunId] = useState("");
  const [selected, setSelected] = useState<Citation | null>(null),
    [liveAsked, setAsked] = useState("");
  const answer = liveAsked ? liveAnswer : (replay.data?.result ?? null);
  const runId = liveAsked ? liveRunId : (replay.data?.id ?? "");
  const asked = liveAsked || replay.data?.question || "";
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const evidence = useQuery({
    queryKey: ["evidence", runId, selected?.evidence_id],
    enabled: !!selected,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/evidence/{evidence_id}", {
          params: {
            path: { evidence_id: selected!.evidence_id },
            query: { run_id: runId },
          },
        }),
      ),
  });
  const trace = useQuery({
    queryKey: ["run", runId],
    enabled: !!runId && !busy,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/runs/{run_id}", {
          params: { path: { run_id: runId } },
        }),
      ),
  });
  const upload = useMutation({
    mutationFn: async ({
      file,
      documentId = null,
    }: {
      file: File;
      documentId?: string | null;
    }) => {
      if (
        file.size > 10 * 1024 * 1024 ||
        !file.name.toLowerCase().endsWith(".pdf")
      )
        throw new Error("pdf_required_max_10_mib");
      const result = await api.POST("/v1/knowledge-bases/{kb_id}/documents", {
        params: {
          path: { kb_id: id },
          query: {
            filename: file.name,
            license,
            ...(documentId ? { document_id: documentId } : {}),
          },
          header: { "idempotency-key": crypto.randomUUID() },
        },
        body: file as unknown as string,
        bodySerializer: () => file,
        headers: { "Content-Type": "application/pdf" },
      });
      return unwrap(result);
    },
    onSuccess: () => {
      setReplacing(null);
      void cache.invalidateQueries({ queryKey: ["documents", id] });
    },
  });
  const example = useMutation({
    mutationFn: async () => {
      const r = await fetch("/original-handbook.pdf");
      if (!r.ok) throw new Error("example_unavailable");
      await upload.mutateAsync({
        file: new File([await r.blob()], "CiteWeave-原创验收手册.pdf", {
          type: "application/pdf",
        }),
      });
    },
  });
  const ready = docs.data?.filter((d) => d.active_version_id).length ?? 0;
  const ask = async () => {
    if (!question.trim() || busy) return;
    const q = question.trim();
    setAsked(q);
    setQuestion("");
    setBusy(true);
    setError("");
    setDraft("");
    setAnswer(null);
    setSelected(null);
    setRunId("");
    setStage("检索中 / retrieving");
    controller.current = new AbortController();
    try {
      const response = await fetch("/v1/queries", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({
          kb_id: id,
          question: q,
          profile,
          ...(profile === "telecom-structural-v1"
            ? {
                evidence_mode: mode,
                ...(scope.length ? { document_ids: scope } : {}),
              }
            : {}),
        }),
        signal: controller.current.signal,
      });
      await readAnswer(response, (event) => {
        if (controller.current?.signal.aborted) return;
        setRunId(event.run_id);
        if (event.type === "stage")
          setStage(
            event.stage === "混合检索与重排"
              ? "检索 / 重排中 · retrieving / reranking"
              : event.stage === "依据证据生成"
                ? "生成中 / generating"
                : (event.stage ?? ""),
          );
        if (event.type === "delta") setDraft((d) => d + (event.text ?? ""));
        if (event.type === "final" && event.answer) {
          setAnswer(event.answer);
          setDraft("");
          setStage("证据引用已校验");
        }
        if (event.type === "error")
          throw new Error(event.code ?? "query_failed");
      });
    } catch (e) {
      setDraft("");
      setAnswer(null);
      setError(
        e instanceof DOMException && e.name === "AbortError"
          ? "回答已停止；本次记录仍可追踪。"
          : message(e),
      );
    } finally {
      setBusy(false);
    }
  };
  function answerContent(value: Answer) {
    return citationParts(value.text).map((part, i) => {
      const citation = citationForPart(part, value.citations);
      return citation ? (
        <button
          key={i}
          className="inline-citation"
          onClick={() => setSelected(citation)}
          aria-label={`查看引用 ${citation.label}`}
        >
          {citation.label}
        </button>
      ) : (
        part
      );
    });
  }
  return (
    <section className="workspace">
      <div className="workspace-title">
        <div>
          <p className="eyebrow">KNOWLEDGE SPACE</p>
          <h1>{kb.data?.name ?? "正在打开…"}</h1>
          <p className="muted">
            {kb.data?.description || "从文档获取答案，用原文验证答案。"}
          </p>
        </div>
        <Link className="ops-link" to={`/documents?kb=${id}`}>
          {ready} 份可用文档 · 检查结构 →
        </Link>
      </div>
      {(kb.error || docs.error) && (
        <p className="error" role="alert">
          {message(kb.error || docs.error)}
        </p>
      )}
      <div className={`work-columns ${selected ? "has-evidence" : ""}`}>
        <aside className="documents">
          <div className="section-heading">
            <h3>资料</h3>
            <span>{docs.data?.length ?? 0} / 10</span>
          </div>
          <details className="upload-disclosure">
            <summary>添加 / 替换 PDF</summary>
            <div className="upload-box">
              <Upload size={23} />
              <strong>添加一份 PDF</strong>
              <p>文字型 PDF · 最大 10 MB</p>
              <label className="sr-only" htmlFor="license">
                文档使用许可
              </label>
              <select
                id="license"
                value={license}
                onChange={(e) => setLicense(e.target.value)}
              >
                <option value="original">我拥有原创内容权利</option>
                <option value="CC0-1.0">CC0 1.0</option>
                <option value="CC-BY-4.0">CC BY 4.0</option>
                <option value="permission-held">已获得使用许可</option>
              </select>
              <input
                ref={fileInput}
                aria-label="上传 PDF 文件"
                type="file"
                accept="application/pdf,.pdf"
                className="file-input"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) upload.mutate({ file, documentId: replacing });
                  e.target.value = "";
                }}
              />
              <Button
                className="wide"
                variant="outline"
                disabled={upload.isPending}
                onClick={() => {
                  setReplacing(null);
                  fileInput.current?.click();
                }}
              >
                {upload.isPending ? "正在上传…" : "选择 PDF"}
              </Button>
              <button
                className="text-button"
                disabled={example.isPending || upload.isPending}
                onClick={() => example.mutate()}
              >
                使用原创示例手册 ↗
              </button>
            </div>
          </details>
          {(upload.error || example.error) && (
            <p className="error" role="alert">
              {message(upload.error || example.error)}
            </p>
          )}
          <div className="document-list">
            {docs.data?.map((doc) => (
              <DocumentCard
                key={doc.id}
                doc={doc}
                onReplace={() => {
                  setReplacing(doc.id);
                  fileInput.current?.click();
                }}
              />
            ))}
          </div>
          {!docs.data?.length && (
            <p className="empty-caption">
              添加文档后，可在这里查看真实处理进度。
            </p>
          )}
        </aside>
        <div className="chat-panel">
          <div className="section-heading">
            <h3>
              <Search size={15} /> 证据问答
            </h3>
            <span>{asked ? "固定来源版本" : "就绪 / idle"}</span>
          </div>
          <div className="query-options">
            <label>
              下一次提问 · 检索路径
              <select
                aria-label="检索路径"
                disabled={busy}
                value={profile}
                onChange={(e) => {
                  setProfile(e.target.value as typeof profile);
                  setScope([]);
                }}
              >
                <option value="m3-context">兼容路径 · Legacy</option>
                <option value="telecom-structural-v1">
                  结构感知 · Telecom
                </option>
              </select>
            </label>
            {profile === "telecom-structural-v1" && (
              <>
                <label>
                  来源模式
                  <select
                    aria-label="来源模式"
                    disabled={busy}
                    value={mode}
                    onChange={(e) => setMode(e.target.value as typeof mode)}
                  >
                    <option value="auto">自动</option>
                    <option value="single">单来源</option>
                    <option value="compare">跨来源比较</option>
                  </select>
                </label>
                <details>
                  <summary>
                    文档范围 ·{" "}
                    {scope.length ? `${scope.length} 份` : "全部可用文档"}
                  </summary>
                  {docs.data
                    ?.filter((d) => d.active_version_id)
                    .map((d) => (
                      <label className="scope-option" key={d.id}>
                        <input
                          type="checkbox"
                          disabled={busy}
                          checked={scope.includes(d.id)}
                          onChange={(e) =>
                            setScope(
                              e.target.checked
                                ? [...scope, d.id]
                                : scope.filter((x) => x !== d.id),
                            )
                          }
                        />
                        {d.title}
                      </label>
                    ))}
                </details>
              </>
            )}
          </div>
          <div className="conversation">
            {!asked && (
              <div className="chat-empty">
                <span className="quote-emblem">
                  <Quote size={30} />
                </span>
                <p className="eyebrow">ASK. TRACE. VERIFY.</p>
                <h2>你想从文档中找到什么？</h2>
                <p>提出一个具体问题。回答生成后，点击引用即可回到原 PDF。</p>
                <button
                  className="suggestion"
                  onClick={() =>
                    setQuestion(
                      "湖畔观测站的温度传感器多久采样一次，原始数据保留多久？",
                    )
                  }
                >
                  示例：采样频率和数据保留时间是什么？ <ArrowUp size={15} />
                </button>
              </div>
            )}
            {asked && (
              <>
                <div className="question-bubble">{asked}</div>
                <div className="answer-block">
                  <div className="answer-author">
                    <span className="mini-logo">C</span>
                    <strong>CiteWeave</strong>
                    <span>
                      {busy
                        ? stage
                        : answer
                          ? answer.citations.length
                            ? "最终答案 / final"
                            : "证据不足 / insufficient evidence"
                          : error?.includes("停止")
                            ? "已取消 / cancelled"
                            : "失败 / failed"}
                    </span>
                  </div>
                  {trace.data && (
                    <p className="replay-notice">
                      {generationLabel(trace.data)}
                    </p>
                  )}
                  {trace.data?.evidence_pack?.degraded && (
                    <p className="warning-banner">
                      降级检索 · BGE 不可用，使用 RRF 种子。
                    </p>
                  )}
                  {trace.data?.evidence_pack?.source_coverage
                    .coverage_unmet && (
                    <p className="warning-banner">
                      来源缺口 · 部分请求来源未进入答案上下文。
                    </p>
                  )}
                  {busy && (
                    <p className="draft-label">
                      <LoaderCircle size={13} className="spin" />
                      临时草稿 · provisional · 引用将在完成时校验
                    </p>
                  )}
                  <div className="answer-text">
                    {answer
                      ? answerContent(answer)
                      : draft || (busy ? "正在查找可用证据…" : "")}
                  </div>
                  {error && (
                    <p className="error" role="alert">
                      {error}
                    </p>
                  )}
                  {answer && (
                    <>
                      <div className="verified-label">
                        <Check size={13} />{" "}
                        {answer.citations.length
                          ? "引用与原文片段一致"
                          : "未提供可引用答案"}{" "}
                        <span>· 不代表语义支持已自动验证</span>
                      </div>
                      <div className="citation-cards">
                        {answer.citations.map((c) => (
                          <button
                            key={c.evidence_id}
                            className={
                              selected?.evidence_id === c.evidence_id
                                ? "citation-card selected"
                                : "citation-card"
                            }
                            onClick={() => setSelected(c)}
                          >
                            <span className="citation-index">{c.label}</span>
                            <div>
                              <strong>{c.filename}</strong>
                              <p>{c.span.quote}</p>
                              <small>
                                第 {c.span.boxes[0].page_index + 1} 页 ·
                                查看原文 ↗
                              </small>
                            </div>
                          </button>
                        ))}
                      </div>
                      <p className="cost-note">
                        {answer.usage ? "Token 用量已记录" : "Token 用量不可用"}{" "}
                        · 估算 ¥{answer.estimated_yuan?.toFixed(6) ?? "不可用"}{" "}
                        · 实际扣费不可用
                      </p>
                    </>
                  )}
                  {trace.data && (
                    <details className="trace">
                      <summary>开发者记录 · {trace.data.status}</summary>
                      <Link className="ops-link" to={`/runs/${runId}`}>
                        打开完整 Run Inspector →
                      </Link>
                      <p>Run {runId}</p>
                      <p>
                        固定 {trace.data.versions.length} 个文档版本；
                        {trace.data.candidates.length} 个检索候选。
                      </p>
                      <pre>
                        {JSON.stringify(
                          trace.data.candidates.map((c) => ({
                            id: c.candidate_id,
                            retrieval: c.retrieval,
                            rrf: c.rrf_score,
                            reranker: c.reranker_score,
                            evidence_rank: c.final_evidence_rank,
                          })),
                          null,
                          2,
                        )}
                      </pre>
                    </details>
                  )}
                </div>
              </>
            )}
          </div>
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              void ask();
            }}
          >
            <label className="sr-only" htmlFor="question">
              输入问题
            </label>
            <textarea
              id="question"
              placeholder={
                ready
                  ? "输入一个关于文档的问题…"
                  : "上传并等待文档处理完成后，即可提问…"
              }
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              maxLength={profile === "telecom-structural-v1" ? 512 : 160}
              rows={2}
              disabled={!ready || busy}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  void ask();
                }
              }}
            />
            <div className="composer-foot">
              <span>
                {question.length} /{" "}
                {profile === "telecom-structural-v1" ? 512 : 160} · Enter 发送
              </span>
              {busy ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => controller.current?.abort()}
                >
                  停止
                </Button>
              ) : (
                <Button
                  type="submit"
                  aria-label="发送问题"
                  disabled={!ready || !question.trim()}
                  size="icon"
                >
                  <ArrowUp />
                </Button>
              )}
            </div>
          </form>
        </div>
        {selected && (
          <aside className="evidence-panel">
            <div className="section-heading">
              <h3>
                原文证据{" "}
                <span className="citation-index">{selected.label}</span>
              </h3>
              <button
                aria-label="关闭证据"
                className="icon-button"
                onClick={() => setSelected(null)}
              >
                <X size={18} />
              </button>
            </div>
            {evidence.isPending && (
              <p className="muted padded">正在验证来源…</p>
            )}
            {evidence.error && (
              <p className="error padded">{message(evidence.error)}</p>
            )}
            {selected && trace.data?.structural_candidates && (
              <p className="padded muted">
                {sectionPath(
                  trace.data.structural_candidates.find(
                    (c) =>
                      c.evidence_ids.includes(selected.evidence_id) ||
                      c.parent_id ===
                        trace.data?.evidence_pack?.spans.find(
                          (s) => s.evidence_id === selected.evidence_id,
                        )?.parent_id,
                  )?.section_path ?? [],
                )}
              </p>
            )}
            {evidence.data && (
              <PdfEvidence
                key={evidence.data.evidence_id}
                citation={evidence.data}
              />
            )}
          </aside>
        )}
      </div>
    </section>
  );
}

function DocumentCard({ doc, onReplace }: { doc: Doc; onReplace: () => void }) {
  const latest = doc.versions[0],
    pending = !["READY", "FAILED_FINAL"].includes(latest.job.status);
  return (
    <article className="document-card">
      <FileText size={18} />
      <div>
        <strong>{doc.title}</strong>
        <p>
          最新上传 v{latest.version.sequence} ·{" "}
          {latest.version.page_count || "—"} 页
        </p>
        {doc.active_version_id && (
          <small>
            当前提问版本 v
            {doc.versions.find((v) => v.version.id === doc.active_version_id)
              ?.version.sequence ?? "历史版本"}
          </small>
        )}
        <span
          className={`status ${latest.job.status === "READY" ? "ready" : latest.job.status === "FAILED_FINAL" ? "failed" : ""}`}
        >
          {pending && <LoaderCircle size={11} className="spin" />}
          {statuses[latest.job.status] ?? latest.job.status}
        </span>
        <small>
          尝试 {latest.job.attempt} / {latest.job.max_attempts}
          {latest.version.chunk_count
            ? ` · ${latest.version.chunk_count} 个片段`
            : ""}
        </small>
        {latest.job.error_message && (
          <p className="error">{latest.job.error_message}</p>
        )}
        {!!doc.active_version_id && latest.job.status !== "READY" && (
          <small>先前完成的版本仍可提问。</small>
        )}
        {!pending && (
          <button className="text-button" onClick={onReplace}>
            上传新版本
          </button>
        )}
        <Link className="text-button" to={`/documents/${doc.id}/versions`}>
          查看版本与重建
        </Link>
      </div>
    </article>
  );
}
