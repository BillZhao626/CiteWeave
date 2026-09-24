import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, listKBs, message, unwrap, type Citation } from "./api";
import { Button } from "./components/ui/button";
import { StructuralTrace } from "./structural-trace";
import { CaseRuntimeView } from "./runtime-view";
import { statusTone, judgmentLabel } from "./product-facts";
import { PdfEvidence } from "./pdf-evidence";
import type { components } from "./generated/api";

type ObjectValue = Record<string, unknown>;
const object = (value: unknown): ObjectValue =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as ObjectValue)
    : {};
const number = (value: unknown) => (typeof value === "number" ? value : null);
const cost = (value: unknown) =>
  number(value) === null ? "不可用" : `¥${Number(value).toFixed(6)}`;
const date = (value: string) =>
  new Date(value).toLocaleString("zh-CN", { hour12: false });
const short = (value: unknown) => String(value ?? "—").slice(0, 12);
const text = (value: unknown) => String(value ?? "—");
function Failure({ error }: { error: unknown }) {
  return error ? (
    <p role="alert" className="error">
      {message(error)}
    </p>
  ) : null;
}
function Page({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <section className="ops-page">
      <p className="eyebrow">CITEWEAVE / DEVELOPER</p>
      <h1>{title}</h1>
      <p className="muted ops-intro">{subtitle}</p>
      {children}
    </section>
  );
}
function Json({
  value,
  label = "配置与详细记录",
}: {
  value: unknown;
  label?: string;
}) {
  return (
    <details className="ops-json">
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
function Pages({
  offset,
  count,
  setOffset,
}: {
  offset: number;
  count: number;
  setOffset: (n: number) => void;
}) {
  return (
    <div className="ops-pager">
      <Button
        variant="outline"
        disabled={!offset}
        onClick={() => setOffset(Math.max(0, offset - 25))}
      >
        上一页
      </Button>
      <span>第 {offset / 25 + 1} 页</span>
      <Button
        variant="outline"
        disabled={count < 25}
        onClick={() => setOffset(offset + 25)}
      >
        下一页
      </Button>
    </div>
  );
}
function Status({ value }: { value: string }) {
  return <span className={`status ${statusTone(value)}`}>{value}</span>;
}
function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note?: string;
}) {
  return (
    <div className="ops-metric">
      <small>{label}</small>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

export function RunsPage() {
  const [offset, setOffset] = useState(0);
  const runs = useQuery({
    queryKey: ["runs", offset],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/runs", { params: { query: { limit: 25, offset } } }),
      ),
    refetchInterval: 5000,
  });
  return (
    <Page
      title="回答记录"
      subtitle="从一次问题出发，复盘证据如何进入最终答案。"
    >
      <Failure error={runs.error} />
      <div className="ops-list">
        {runs.data?.map((run) => (
          <Link className="ops-row" to={`/runs/${run.id}`} key={run.id}>
            <div>
              <strong>{run.question}</strong>
              <small>
                {date(run.created_at)} · {short(run.id)}
              </small>
            </div>
            <Status value={run.status} />
            <span>{cost(run.estimated_yuan)}</span>
          </Link>
        ))}
      </div>
      {runs.isPending && <p>正在读取记录…</p>}
      {runs.data?.length === 0 && (
        <p className="empty-caption">
          提出第一个问题后，这里会保留回答与诊断记录。
        </p>
      )}
      <Pages
        offset={offset}
        count={runs.data?.length ?? 0}
        setOffset={setOffset}
      />
    </Page>
  );
}

export function RunInspector() {
  const { id = "" } = useParams();
  const [branch, setBranch] = useState("final"),
    [selected, setSelected] = useState<Citation | null>(null);
  const run = useQuery({
    queryKey: ["run", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/runs/{run_id}", {
          params: { path: { run_id: id } },
        }),
      ),
    refetchInterval: (query) =>
      query.state.data?.status === "RUNNING" ? 2000 : false,
  });
  const evidence = useQuery({
    queryKey: ["inspector-evidence", id, selected?.evidence_id],
    enabled: !!selected,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/evidence/{evidence_id}", {
          params: {
            path: { evidence_id: selected!.evidence_id },
            query: { run_id: id },
          },
        }),
      ),
  });
  const row = run.data;
  const candidates: (ObjectValue & { rank: unknown; score: unknown })[] = (
    row?.candidates ?? []
  )
    .flatMap((c) => {
      const hits = Array.isArray(c.retrieval) ? c.retrieval.map(object) : [];
      if (branch === "dense" || branch === "bm25")
        return hits
          .filter((h) => h.source === branch)
          .map((h) => ({ ...c, rank: h.rank, score: h.score }));
      const rank =
        branch === "final"
          ? c.final_evidence_rank
          : branch === "reranker"
            ? c.reranker_rank
            : branch === "input"
              ? c.rerank_input_rank
              : c.rrf_rank;
      return rank
        ? [
            {
              ...c,
              rank,
              score: branch === "rrf" ? c.rrf_score : c.reranker_score,
            },
          ]
        : [];
    })
    .sort((a, b) => Number(a.rank) - Number(b.rank));
  return (
    <Page
      title="Run Inspector"
      subtitle="检索、重排、生成与引用校验使用同一个运行标识。"
    >
      <Link className="ops-link" to="/runs">
        ← 回答记录
      </Link>
      <Failure error={run.error} />
      {run.isPending && <p>正在读取链路…</p>}
      {row && (
        <>
          <div className="ops-panel">
            <div className="ops-heading">
              <h2>{row.question}</h2>
              <Status value={row.status} />
            </div>
            <p className="ops-id">{row.id}</p>
            <Link className="ops-link" to={`/kb/${row.kb_id}?run=${row.id}`}>
              在 Ask 中查看答案 →
            </Link>
            <dl className="runtime-summary">
              <div>
                <dt>Provider / Model</dt>
                <dd>
                  {text(row.runtime_config.provider)} /{" "}
                  {text(row.runtime_config.model)}
                </dd>
              </div>
              <div>
                <dt>Prompt</dt>
                <dd>{text(row.runtime_config.prompt_identity)}</dd>
              </div>
              <div>
                <dt>Runtime</dt>
                <dd>{text(row.runtime_config.release_identity)}</dd>
              </div>
              <div>
                <dt>Citation linkage</dt>
                <dd>
                  {row.result?.citations
                    .map((c) => `[${c.label}]`)
                    .join(" · ") || "无可引用答案"}
                </dd>
              </div>
            </dl>
            <div className="ops-metrics">
              <Metric label="文档版本" value={row.versions.length} />
              <Metric
                label="输入 / 输出 token"
                value={`${text(row.usage?.prompt_tokens)} / ${text(row.usage?.completion_tokens)}`}
              />
              <Metric
                label="估算费用"
                value={cost(row.estimated_yuan)}
                note="实际扣费 unavailable"
              />
              <Metric
                label="上游调用 / 重试"
                value={`${row.calls.length} / ${row.calls.filter((c) => Number(c.attempt) > 1).length}`}
              />
            </div>
            {row.error_code && (
              <p className="error">
                {row.error_code} · {row.error_category}
              </p>
            )}
            <Json
              label="固定版本、索引与运行配置"
              value={{
                versions: row.versions,
                index_bindings: row.index_bindings,
                config: row.runtime_config,
              }}
            />
          </div>
          <div className="ops-panel">
            <h2>执行链路 / 阶段耗时</h2>
            <p className="muted">
              记录顺序 · 阶段可能嵌套，耗时不累加为总延迟。
            </p>
            {!row.stages.length && (
              <p className="muted">这条历史记录未采集阶段耗时。</p>
            )}
            <div className="ops-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>阶段</th>
                    <th>状态</th>
                    <th>输入 → 输出</th>
                    <th>耗时 ms</th>
                  </tr>
                </thead>
                <tbody>
                  {row.stages.map((s, i) => (
                    <tr key={i}>
                      <td>
                        <strong>{text(s.name)}</strong>
                        <small>{s.version_id ? short(s.version_id) : ""}</small>
                      </td>
                      <td>{text(s.status)}</td>
                      <td>
                        {text(s.input_count)} →{" "}
                        {text(s.output_count ?? s.output_chars)}
                      </td>
                      <td>{number(s.latency_ms)?.toFixed(1) ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Json label="阶段时间戳和配置" value={row.stages} />
          </div>
          <div className="ops-panel">
            {row.trace_schema_revision === "structural-trace-v1" ? (
              <StructuralTrace run={row} />
            ) : (
              <>
                <h2>证据的筛选过程</h2>
                <div className="ops-tabs">
                  {[
                    ["dense", "Dense"],
                    ["bm25", "BM25"],
                    ["rrf", "RRF"],
                    ["input", "重排输入"],
                    ["reranker", "Reranker"],
                    ["final", "最终证据"],
                  ].map(([key, label]) => (
                    <button
                      key={key}
                      aria-pressed={branch === key}
                      onClick={() => setBranch(key)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <p className="muted">
                  {candidates.length} 条 · Dense / BM25
                  的名次与分数按文档版本解释。
                </p>
                <div className="ops-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>排名</th>
                        <th>片段</th>
                        <th>分数</th>
                        <th>文档版本</th>
                      </tr>
                    </thead>
                    <tbody>
                      {candidates.map((c, i) => (
                        <tr key={`${text(c.candidate_id)}-${i}`}>
                          <td>{text(c.rank)}</td>
                          <td>
                            <p>{text(c.text ?? c.candidate_id)}</p>
                            <small>{short(c.candidate_id)}</small>
                            {!!c.duplicate_of && (
                              <small>
                                同版本重复 → {short(c.duplicate_of)}
                              </small>
                            )}
                            {!!c.context_seed && (
                              <small>
                                相邻原文 · seed {short(c.context_seed)}
                              </small>
                            )}
                          </td>
                          <td>{number(c.score)?.toFixed(4) ?? "—"}</td>
                          <td title={text(c.document_version_id)}>
                            {short(c.document_version_id)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
          <div className="ops-panel">
            <h2>最终答案与引用</h2>
            <p className="answer-text">
              {row.result?.text ?? "没有通过校验的最终答案。"}
            </p>
            <div className="citation-cards">
              {row.result?.citations.map((c) => (
                <button
                  key={c.evidence_id}
                  className="citation-card"
                  onClick={() => setSelected(c)}
                >
                  <span className="citation-index">{c.label}</span>
                  <div>
                    <strong>
                      {c.filename} · PDF 第 {c.span.boxes[0].page_index + 1} 页
                    </strong>
                    <p>{c.span.quote}</p>
                    <small>打开原文与精确高亮 ↗</small>
                  </div>
                </button>
              ))}
            </div>
            <Failure error={evidence.error} />
            {evidence.data && (
              <PdfEvidence
                key={evidence.data.evidence_id}
                citation={evidence.data}
              />
            )}
          </div>
          <div className="ops-panel">
            <h2>上游调用与费用</h2>
            <div className="ops-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>调用</th>
                    <th>尝试</th>
                    <th>结果</th>
                    <th>耗时 ms</th>
                    <th>费用估算</th>
                  </tr>
                </thead>
                <tbody>
                  {row.calls.map((call, i) => (
                    <tr key={i}>
                      <td>
                        {text(call.upstream)}
                        <small>{text(call.operation)}</small>
                      </td>
                      <td>{text(call.attempt)}</td>
                      <td>
                        {text(call.status)}
                        <small>{text(call.error_code ?? call.outcome)}</small>
                      </td>
                      <td>{number(call.latency_ms)?.toFixed(1)}</td>
                      <td>{cost(call.estimated_yuan)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Json
              label="逐次 usage、输入 / 输出费用与错误分类"
              value={row.calls}
            />
          </div>
        </>
      )}
    </Page>
  );
}

export function EvaluationsPage() {
  const cache = useQueryClient(),
    [offset, setOffset] = useState(0),
    [kbId, setKbId] = useState(""),
    [split, setSplit] = useState<
      "dev" | "test" | "all" | "regression" | "safety"
    >("dev"),
    [dataset, setDataset] = useState<
      "public-standards-v1" | "citeweave-public-telecom-eval-v1"
    >("citeweave-public-telecom-eval-v1");
  const kbs = useQuery({ queryKey: ["kbs"], queryFn: listKBs });
  const runs = useQuery({
    queryKey: ["evaluations", offset],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/evaluations", {
          params: { query: { limit: 25, offset } },
        }),
      ),
    refetchInterval: 5000,
  });
  const create = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/v1/evaluations", {
          body: {
            kb_id: kbId,
            dataset_id: dataset,
            split,
            profile:
              dataset === "citeweave-public-telecom-eval-v1"
                ? "telecom-structural-v1"
                : "m3-context",
            judge_profile: "judge-v4",
          },
          params: { header: { "idempotency-key": crypto.randomUUID() } },
        }),
      ),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["evaluations"] });
    },
  });
  return (
    <Page
      title="评测"
      subtitle="使用冻结问题集比较检索、证据覆盖、回答质量和引用定位。"
    >
      <div className="ops-panel">
        <h2>冻结数据集与评测</h2>
        <label>
          数据集
          <select
            aria-label="评测数据集"
            value={dataset}
            onChange={(e) => {
              setDataset(e.target.value as typeof dataset);
              setSplit("dev");
            }}
          >
            <option value="citeweave-public-telecom-eval-v1">
              CiteWeave independent public telecom corpus
            </option>
            <option value="public-standards-v1">
              历史 public-standards-v1
            </option>
          </select>
        </label>
        <p className="muted">
          {dataset === "citeweave-public-telecom-eval-v1"
            ? "72 个可见案例 · Dev 32 / Regression 24 / Safety 16。Holdout: NOT_YET_SEALED · 24 题待独立封存。AI/source-grounded labels，不是 Human Gold。"
            : "历史数据集 · 48 题 · Dev/Test 各 24；历史结果不代表新语料质量。"}
        </p>
        <div className="ops-form">
          <label>
            知识库
            <select value={kbId} onChange={(e) => setKbId(e.target.value)}>
              <option value="">选择知识库</option>
              {kbs.data?.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            数据划分
            <select
              value={split}
              onChange={(e) => setSplit(e.target.value as typeof split)}
            >
              {dataset === "citeweave-public-telecom-eval-v1" ? (
                <>
                  <option value="dev">Development · 32</option>
                  <option value="regression">Regression · 24</option>
                  <option value="safety">Safety · 16</option>
                </>
              ) : (
                <>
                  <option value="dev">Development · 24</option>
                  <option value="test">Frozen Test · 24</option>
                  <option value="all">全部 · 48</option>
                </>
              )}
            </select>
          </label>
          <Button
            disabled={!kbId || create.isPending}
            onClick={() => create.mutate()}
          >
            启动已配置 Provider 的评测
          </Button>
        </div>
        <p className="muted">
          后台逐题执行并记录 API
          估算费用。测试集用于冻结比较，不能按测试结果反复调参。
        </p>
        <Failure error={create.error} />
        {create.data && (
          <Link className="ops-link" to={`/evaluations/${create.data.id}`}>
            已创建，查看运行 →
          </Link>
        )}
      </div>
      <Failure error={runs.error} />
      <div className="ops-list">
        {runs.data?.map((r) => (
          <Link to={`/evaluations/${r.id}`} key={r.id} className="ops-row">
            <div>
              <strong>
                {r.dataset_id} / {r.split}
              </strong>
              <small>
                {date(r.created_at)} · {short(r.id)}
              </small>
            </div>
            <Status value={r.status} />
          </Link>
        ))}
      </div>
      <Pages
        offset={offset}
        count={runs.data?.length ?? 0}
        setOffset={setOffset}
      />
    </Page>
  );
}

export function EvaluationDetail() {
  const cache = useQueryClient();
  const { id = "" } = useParams(),
    [offset, setOffset] = useState(0),
    [expanded, setExpanded] = useState("");
  const evaluation = useQuery({
    queryKey: ["evaluation", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/evaluations/{eval_id}", {
          params: { path: { eval_id: id } },
        }),
      ),
    refetchInterval: (query) =>
      ["RUNNING", "PENDING"].includes(query.state.data?.status ?? "")
        ? 4000
        : false,
  });
  const cases = useQuery({
    queryKey: ["eval-cases", id, offset],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/evaluations/{eval_id}/cases", {
          params: { path: { eval_id: id }, query: { limit: 25, offset } },
        }),
      ),
    refetchInterval: 5000,
  });
  const summary = object(evaluation.data?.summary),
    retrieval = object(summary.retrieval),
    ev = object(summary.evidence),
    citations = object(summary.citation),
    answer = object(summary.answer);
  const cancel = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/v1/evaluations/{eval_id}/cancel", {
          params: { path: { eval_id: id } },
        }),
      ),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["evaluation", id] });
      void cache.invalidateQueries({ queryKey: ["eval-cases", id] });
    },
  });
  const metric = (value: unknown) => {
    const v = object(value);
    return number(v.mean) === null
      ? "不可用"
      : `${(Number(v.mean) * 100).toFixed(1)}% · n=${text(v.denominator)}`;
  };
  return (
    <Page
      title="评测报告"
      subtitle="指标对应这份小型标准文档数据集；Judge 分数是辅助判断，不能视为绝对真值。"
    >
      <Link className="ops-link" to="/evaluations">
        ← 全部评测
      </Link>
      <Failure error={evaluation.error || cases.error || cancel.error} />
      {evaluation.data && (
        <>
          <div className="ops-panel">
            <div className="ops-heading">
              <h2>
                {evaluation.data.dataset_id} / {evaluation.data.split}
              </h2>
              <Status value={evaluation.data.status} />
            </div>
            <p className="ops-id">{id}</p>
            <p className="ops-notice">
              {evaluation.data.dataset_id === "fixture"
                ? "TEST FIXTURE · 原创故障注入记录 · 不是语料质量评测"
                : evaluation.data.dataset_id ===
                    "citeweave-public-telecom-eval-v1"
                  ? "AI / source-grounded labels · 未经人审的标签不是 Human Gold。Holdout: NOT_YET_SEALED。"
                  : "历史评测 · 不代表当前结构语料质量"}
            </p>
            <div className="state-counts">
              {Object.entries(object(summary.case_status)).map(
                ([state, count]) => (
                  <span key={state}>
                    <Status value={state} /> {text(count)}
                  </span>
                ),
              )}
            </div>
            <Json
              label="完整性 / 失败分母 / 缺失语义判断"
              value={{
                completeness: evaluation.data.completeness,
                quality_accounting: summary.quality_accounting,
              }}
            />
            <div className="ops-metrics">
              <Metric
                label="已评估 / 总题数"
                value={`${text(summary.assessed_count)} / ${text(summary.case_count)}`}
              />
              <Metric label="最终证据覆盖" value={metric(ev.final)} />
              <Metric
                label="引用重新定位通过"
                value={metric(citations.grounded_rate)}
              />
              <Metric
                label="回答完整度 · Judge"
                value={metric(answer.completeness)}
              />
            </div>
            <div className="ops-actions">
              {["PENDING", "RUNNING"].includes(evaluation.data.status) && (
                <Button
                  variant="outline"
                  disabled={cancel.isPending}
                  onClick={() => cancel.mutate()}
                >
                  停止后续题目
                </Button>
              )}
              <a
                href={`/v1/evaluations/${id}/artifact`}
                target="_blank"
                rel="noreferrer"
                className="ops-link"
              >
                JSON 工件 ↗
              </a>
              <a
                href={`/v1/evaluations/${id}/report`}
                target="_blank"
                rel="noreferrer"
                className="ops-link"
              >
                Markdown 报告 ↗
              </a>
            </div>
            {["PENDING", "RUNNING", "CANCELLED"].includes(
              evaluation.data.status,
            ) && (
              <p className="muted">
                取消由 PostgreSQL 提交并使旧 owner
                失效。已经发出的上游请求无法召回；未知费用仍保留。
              </p>
            )}
            <Json
              label="冻结配置与数据集哈希"
              value={{
                hash: evaluation.data.dataset_hash,
                config: evaluation.data.runtime_config,
                versions: evaluation.data.versions,
              }}
            />
          </div>
          <div className="ops-panel">
            <h2>检索指标 · Recall@20 / MRR@10 / nDCG@10</h2>
            <div className="ops-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>阶段</th>
                    <th>Recall</th>
                    <th>MRR</th>
                    <th>nDCG</th>
                  </tr>
                </thead>
                <tbody>
                  {["dense", "bm25", "rrf", "reranked"].map((s) => {
                    const m = object(object(retrieval[s])["20"]);
                    const rank10 = object(object(retrieval[s])["10"]);
                    return (
                      <tr key={s}>
                        <td>{s}</td>
                        <td>{metric(m.recall)}</td>
                        <td>{metric(rank10.mrr)}</td>
                        <td>{metric(rank10.ndcg)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Json label="全部指标、坏案例与人工复核对照" value={summary} />
          </div>
        </>
      )}
      <div className="ops-panel">
        <h2>逐题结果</h2>
        <p className="muted">
          FAILED / CANCELLED / OUTCOME_UNKNOWN 保留在总题数；缺少判断不折算为 0
          分。
        </p>
        {cases.data?.map((c) => (
          <div key={c.case_id} className="ops-case">
            <button
              className="ops-case-heading"
              onClick={() =>
                setExpanded(expanded === c.case_id ? "" : c.case_id)
              }
            >
              <div>
                <strong>{c.case_id}</strong>
                <p>{text(c.result.question ?? "此记录未保存题面")}</p>
              </div>
              <Status value={c.status} />
            </button>
            {expanded === c.case_id && (
              <>
                <CaseRuntimeView evaluationId={id} value={c} />
                <p className="answer-text">
                  {text(object(c.result.answer).text ?? "无有效答案")}
                </p>
                <p className="muted">
                  {judgmentLabel(c.judge)} ·{" "}
                  {text(object(c.judge.scores).verdict)} ·{" "}
                  {text(object(c.judge.scores).reason)}
                </p>
                {!!c.human_review.verdict && (
                  <p className="ops-notice">
                    用户提交复核：
                    {text(
                      c.human_review.human_review ?? c.human_review.verdict,
                    )}{" "}
                    · AI 辅助材料审阅
                  </p>
                )}
                <Json
                  label="事实句与其引用的语义支持（独立于 PDF 定位）"
                  value={
                    object(c.judge.scores).unit_assessments ??
                    object(c.judge.scores).claims ??
                    "未评估"
                  }
                />
                {c.query_run_id && (
                  <Link className="ops-link" to={`/runs/${c.query_run_id}`}>
                    在 Run Inspector 中复盘 →
                  </Link>
                )}
                <Json
                  label="证据 / 引用指标与人工复核"
                  value={{
                    assessment: c.result.assessment,
                    judge: c.judge,
                    human_review: c.human_review,
                  }}
                />
              </>
            )}
          </div>
        ))}
        <Pages
          offset={offset}
          count={cases.data?.length ?? 0}
          setOffset={setOffset}
        />
      </div>
      {evaluation.data?.status === "COMPLETED" && (
        <EvaluationComparison evaluation={evaluation.data} />
      )}
    </Page>
  );
}

function EvaluationComparison({
  evaluation,
}: {
  evaluation: components["schemas"]["Evaluation"];
}) {
  const [baseline, setBaseline] = useState("");
  const [selected, setSelected] = useState("");
  const runs = useQuery({
    queryKey: ["comparison-options"],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/evaluations", { params: { query: { limit: 100 } } }),
      ),
  });
  const comparison = useQuery({
    queryKey: ["comparison", evaluation.id, baseline],
    enabled: !!baseline,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/evaluations/{eval_id}/compare", {
          params: {
            path: { eval_id: evaluation.id },
            query: { baseline_id: baseline },
          },
        }),
      ),
  });
  const rows = Array.isArray(comparison.data?.cases)
    ? comparison.data.cases.map(object)
    : [];
  const row = rows.find((c) => c.case_id === selected);
  return (
    <div className="ops-panel">
      <h2>同题对比</h2>
      <p className="muted">
        选择相同数据划分和 Judge 版本的已完成运行。逐题查看变化，再进入
        Inspector 核对阶段排名。
      </p>
      <label>
        基线运行{" "}
        <select
          aria-label="基线运行"
          value={baseline}
          onChange={(e) => {
            setBaseline(e.target.value);
            setSelected("");
          }}
        >
          <option value="">选择基线</option>
          {runs.data
            ?.filter(
              (r) =>
                r.id !== evaluation.id &&
                r.status === "COMPLETED" &&
                r.split === evaluation.split &&
                r.dataset_hash === evaluation.dataset_hash &&
                r.runtime_config.judge_prompt_sha256 ===
                  evaluation.runtime_config.judge_prompt_sha256,
            )
            .map((r) => (
              <option key={r.id} value={r.id}>
                {date(r.created_at)} · {text(r.runtime_config.query_profile)} ·{" "}
                {short(r.id)}
              </option>
            ))}
        </select>
      </label>
      <Failure error={comparison.error || runs.error} />
      {comparison.isFetching && <p className="muted">加载比较…</p>}
      {comparison.data && (
        <>
          <Json
            label="各指标胜 / 平 / 负与分母"
            value={comparison.data.paired}
          />
          <div className="ops-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>题目</th>
                  <th>正确性</th>
                  <th>完整度</th>
                  <th>证据支持</th>
                  <th>查看</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={text(c.case_id)}>
                    <td>
                      {text(c.case_id)}
                      <small>{text(c.question)}</small>
                    </td>
                    {["correctness", "completeness", "faithfulness"].map(
                      (key) => (
                        <td key={key}>{text(object(c.changes)[key])}</td>
                      ),
                    )}
                    <td>
                      <Button
                        variant="outline"
                        onClick={() => setSelected(text(c.case_id))}
                      >
                        对比
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {row && (
            <div className="comparison-columns">
              {["baseline", "candidate"].map((side) => {
                const value = object(row[side]);
                return (
                  <article className="ops-case" key={side}>
                    <h3>
                      {side === "baseline" ? "基线" : "候选"} ·{" "}
                      {text(row.case_id)}
                    </h3>
                    <p className="answer-text">{text(value.answer)}</p>
                    <p className="muted">
                      {number(value.latency_ms)?.toFixed(0)} ms ·{" "}
                      {cost(value.estimated_yuan)}
                    </p>
                    <Link
                      className="ops-link"
                      to={`/runs/${text(value.query_run_id)}`}
                    >
                      复盘该次运行 →
                    </Link>
                    <Json
                      label="最终证据、分数与引用定位"
                      value={{
                        evidence: value.evidence,
                        coverage: value.coverage,
                        scores: value.scores,
                        physical: value.physical_citation,
                      }}
                    />
                  </article>
                );
              })}
            </div>
          )}
          <Json label="完整对比与适用边界" value={comparison.data} />
        </>
      )}
    </div>
  );
}

export function VersionsPage() {
  const { id = "" } = useParams(),
    cache = useQueryClient(),
    [offset, setOffset] = useState(0);
  const versions = useQuery({
    queryKey: ["versions", id, offset],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/documents/{document_id}/versions", {
          params: { path: { document_id: id }, query: { limit: 25, offset } },
        }),
      ),
    refetchInterval: 4000,
  });
  const action = useMutation({
    mutationFn: async ({
      version,
      kind,
    }: {
      version: string;
      kind: "rebuild" | "rollback";
    }) => {
      const header = { "idempotency-key": crypto.randomUUID() };
      return kind === "rebuild"
        ? unwrap(
            await api.POST("/v1/document-versions/{version_id}/rebuild", {
              params: { path: { version_id: version }, header },
            }),
          )
        : unwrap(
            await api.POST("/v1/documents/{document_id}/rollback", {
              params: { path: { document_id: id }, header },
              body: {
                target_version_id: version,
                expected_active_version_id: versions.data!.active_version_id!,
              },
            }),
          );
    },
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["versions", id] });
      void cache.invalidateQueries({ queryKey: ["documents"] });
    },
  });
  return (
    <Page
      title="文档版本"
      subtitle="切换当前发布版本。历史答案继续引用它当时使用的原始 PDF。"
    >
      <Failure error={versions.error || action.error} />
      {action.data && (
        <p className="ops-notice">
          操作状态：{action.data.status}。
          <Link className="ops-link" to="/system">
            查看后台任务 →
          </Link>
        </p>
      )}
      {versions.data?.versions.map((v) => (
        <div className="ops-panel" key={v.id}>
          <div className="ops-heading">
            <h2>
              {v.filename} · v{v.sequence}
            </h2>
            <Status value={v.status} />
          </div>
          <p className="ops-id">{v.id}</p>
          {versions.data.active_version_id === v.id && (
            <span className="chip">当前发布版本</span>
          )}
          <p className="muted">
            {v.page_count} 页 · {v.chunk_count} 个片段 · {date(v.created_at)}
          </p>
          <div className="ops-actions">
            <Button
              variant="outline"
              disabled={v.status !== "READY" || action.isPending}
              onClick={() => action.mutate({ version: v.id, kind: "rebuild" })}
            >
              重建派生索引
            </Button>
            <Button
              disabled={
                v.status !== "READY" ||
                versions.data.active_version_id === v.id ||
                action.isPending ||
                !versions.data.active_version_id
              }
              onClick={() => action.mutate({ version: v.id, kind: "rollback" })}
            >
              切换为当前版本
            </Button>
          </div>
          <Json
            label="原件哈希与索引身份"
            value={{
              sha256: v.source_sha256,
              index: v.index_collection,
              profile: v.profile,
            }}
          />
        </div>
      ))}
      <Pages
        offset={offset}
        count={versions.data?.versions.length ?? 0}
        setOffset={setOffset}
      />
    </Page>
  );
}

export function SystemPage() {
  const cache = useQueryClient(),
    [offset, setOffset] = useState(0),
    [showGC, setShowGC] = useState(false),
    [gcOffset, setGCOffset] = useState(0);
  const system = useQuery({
    queryKey: ["system"],
    queryFn: async () => unwrap(await api.GET("/v1/system")),
    refetchInterval: 5000,
  });
  const broker = useQuery({
    queryKey: ["broker"],
    queryFn: async () => unwrap(await api.GET("/v1/runtime/broker")),
    refetchInterval: 10000,
  });
  const jobs = useQuery({
    queryKey: ["jobs", offset],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/jobs", { params: { query: { limit: 25, offset } } }),
      ),
    refetchInterval: 4000,
  });
  const gc = useQuery({
    queryKey: ["gc", gcOffset],
    enabled: showGC,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/indexes/gc", {
          params: { query: { limit: 25, offset: gcOffset } },
        }),
      ),
  });
  const remove = useMutation({
    mutationFn: async (name: string) =>
      unwrap(
        await api.POST("/v1/indexes/gc", {
          body: { name },
          params: { header: { "idempotency-key": crypto.randomUUID() } },
        }),
      ),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["gc"] });
    },
  });
  const row = system.data;
  return (
    <Page
      title="系统与任务"
      subtitle="检查后台处理、上游健康、费用预留和索引清理记录。"
    >
      <Failure error={system.error || jobs.error || gc.error || remove.error} />
      {row && (
        <div className="ops-panel">
          <div className="ops-metrics">
            <Metric
              label="Redis / PING"
              value={`${broker.data?.version ?? "不可用"} / ${broker.data?.ping ? "OK" : "不可用"}`}
              note="PostgreSQL 是业务事实来源"
            />
            <Metric label="本地模型" value={text(row.model_gateway.status)} />
            <Metric label="回答次数" value={row.query_count} />
            <Metric
              label="累计已知估算"
              value={cost(row.known_estimated_yuan)}
              note="含评测 Judge，不等同于账单"
            />
            <Metric
              label="未知费用预留"
              value={cost(row.unknown_reserved_yuan)}
            />
          </div>
          <div className="ops-actions">
            {row.circuits.map((c) => (
              <span key={text(c.name)}>
                {text(c.name)} <Status value={text(c.state)} /> · 失败{" "}
                {text(c.failures)}
              </span>
            ))}
          </div>
          <Json
            label="队列限额与恢复探测状态"
            value={{
              model: row.model_gateway,
              circuits: row.circuits,
              jobs: row.jobs,
            }}
          />
        </div>
      )}
      <div className="ops-panel">
        <h2>后台任务</h2>
        {jobs.data?.map((job) => (
          <JobView key={job.id} job={job} />
        ))}
        <Pages
          offset={offset}
          count={jobs.data?.length ?? 0}
          setOffset={setOffset}
        />
      </div>
      <div className="ops-panel">
        <h2>安全索引清理</h2>
        <p className="muted">
          预览会说明每个索引的保护原因。删除操作执行前再次检查引用，并保留审计记录。
        </p>
        <Button
          variant="outline"
          onClick={() => {
            setShowGC(true);
            void gc.refetch();
          }}
        >
          预览 GC · dry-run
        </Button>
        {remove.data && <p>清理结果：{remove.data.status}</p>}
        {showGC && (
          <>
            <div className="ops-list">
              {gc.data?.map((item) => (
                <div className="ops-row" key={item.name}>
                  <div>
                    <strong className="ops-id">{item.name}</strong>
                    <small>{item.reasons.join(" · ")}</small>
                  </div>
                  <Status value={item.disposition} />
                  {item.disposition === "candidate" && (
                    <Button
                      variant="outline"
                      disabled={remove.isPending}
                      onClick={() => remove.mutate(item.name)}
                    >
                      删除候选索引
                    </Button>
                  )}
                </div>
              ))}
            </div>
            <Pages
              offset={gcOffset}
              count={gc.data?.length ?? 0}
              setOffset={setGCOffset}
            />
          </>
        )}
      </div>
    </Page>
  );
}

function JobView({ job }: { job: components["schemas"]["Job"] }) {
  return (
    <details className="ops-job">
      <summary>
        <div>
          <strong>{job.kind === "rebuild" ? "索引重建" : "文档处理"}</strong>
          <small>
            {short(job.id)} · {date(job.created_at)}
          </small>
        </div>
        <Status value={job.status} />
        <span>
          尝试 {job.attempt}/{job.max_attempts}
        </span>
      </summary>
      {job.error_code && <p className="error">{job.error_code}</p>}
      <Json label="任务事件" value={job.events} />
    </details>
  );
}
