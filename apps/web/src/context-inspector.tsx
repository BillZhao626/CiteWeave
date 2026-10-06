import { Link, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  GitBranch,
  LockKeyhole,
  Search,
  Quote,
} from "lucide-react";
import { api, message, unwrap } from "./api";
import type { components } from "./generated/api";
import type { Inspection } from "./publication-inspector";
import "./context-inspector.css";

export type ContextObservation = components["schemas"]["ContextObservation"];
type Summary = components["schemas"]["ConversationRunSummary"];
const short = (id: string) => id.slice(0, 8);

export function ContextView({
  value,
  context,
}: {
  value: Inspection;
  context: ContextObservation;
}) {
  const trace = value.trace;
  const observed = context.availability === "VERIFIED_LOCAL_RECEIPT";
  const relevant = context.candidates?.filter((s) => s.relevant) ?? [];
  const recent = context.candidates?.filter((s) => s.recent_candidate) ?? [];
  const current = value.run.accepted?.result;
  const citations =
    current?.kind === "documentary_answer" ? current.citations : [];
  return (
    <div className="context-body">
      <div className="context-purpose">
        <span>
          <GitBranch size={18} /> History / State <ArrowRight size={15} />{" "}
          理解当前请求
        </span>
        <span>
          <Search size={18} /> Current Evidence <ArrowRight size={15} />{" "}
          支持本轮答案
        </span>
      </div>
      <section className="context-request" aria-label="Current request">
        <div>
          <span className="eyebrow">CURRENT REQUEST</span>
          <h2>{trace.original_question}</h2>
        </div>
        <span className="context-badge">
          {value.run.status} ·{" "}
          {value.publication.decision === "PUBLISHED" ? "已发布" : "未发布"}
        </span>
        <div className="context-resolution" aria-label="指代与省略解析">
          <span className="eyebrow">REFERENCE / INTERPRETATION</span>
          {observed ? (
            <>
              {context.references?.length ? (
                context.references.map((ref, i) => (
                  <p key={i}>
                    <mark>“{ref.mention}”</mark>
                    <ArrowRight size={16} />
                    <span>{ref.values.join(" / ")}</span>
                    <small>
                      原请求 [{ref.start}, {ref.end}) ·{" "}
                      {ref.sources
                        .map((s) => `Turn ${short(s.turn_id)}`)
                        .join(" / ")}
                    </small>
                  </p>
                ))
              ) : context.inherited_facts?.length ? (
                context.inherited_facts.map((fact, i) => (
                  <p key={i}>
                    <mark>继承语境 · {fact.kind}</mark>
                    <ArrowRight size={16} />
                    <span>{fact.value}</span>
                    <small>
                      来源 Turn {short(fact.source!.turn_id)} · 未记录独立指代
                      span
                    </small>
                  </p>
                ))
              ) : (
                <p>未记录显式指代绑定或继承语境。</p>
              )}
              <div className="context-decision">
                <span>主题关系：{context.topic_relation}</span>
                <span>历史依赖：{context.dependency}</span>
                <span>解释模式：{trace.interpretation_mode}</span>
              </div>
            </>
          ) : (
            <p>
              候选与指代细节
              {context.availability === "NOT_RECORDED" ? "未记录" : "无法核对"}
              ；下方保留已发布 Trace 事实。
            </p>
          )}
          <div className="context-query">
            <small>实际检索问题 · SELECTED QUERY</small>
            <p>{trace.selected_query ?? "未记录 / 不可用"}</p>
          </div>
        </div>
      </section>
      <div className="context-grid">
        <div className="context-memory">
          <section className="context-card" aria-label="Relevant History">
            <header>
              <span className="eyebrow">RELEVANT HISTORY</span>
              <span className="context-count">
                {observed
                  ? relevant.length
                  : (trace.history_sources?.length ?? "—")}
              </span>
            </header>
            <h3>本轮明确选中的历史</h3>
            {observed ? (
              relevant.length ? (
                relevant.map((s) => (
                  <div
                    className="context-history-item"
                    key={s.source.acceptance_id}
                  >
                    <p>{s.question}</p>
                    <span className="context-selection">
                      relevant_sources · 显式选择
                    </span>
                    <small>
                      Turn {short(s.source.turn_id)} · Acceptance{" "}
                      {short(s.source.acceptance_id)}
                    </small>
                    {context.references?.some((r) =>
                      r.sources.some(
                        (ref) => ref.acceptance_id === s.source.acceptance_id,
                      ),
                    ) && <small>选中来源用于上方指代 / 省略解析</small>}
                  </div>
                ))
              ) : (
                <p>本轮明确没有选中相关历史。</p>
              )
            ) : (
              <>
                {trace.history_sources?.map((s) => (
                  <p key={s.acceptance_id}>
                    Turn {short(s.turn_id)} · Acceptance{" "}
                    {short(s.acceptance_id)}
                  </p>
                ))}
                <p className="muted">候选原问题与选择细节未核对。</p>
              </>
            )}
            <p className="context-note">
              历史提供请求语境，不提供文档事实依据。
            </p>
          </section>
          <section className="context-card" aria-label="Recent History">
            <header>
              <span className="eyebrow">RECENT HISTORY</span>
              <span className="context-count">
                {observed ? recent.length : "—"}
              </span>
            </header>
            <h3>参与检查的近期候选</h3>
            {observed ? (
              recent.length ? (
                recent.map((s) => (
                  <div
                    className="context-recent-item"
                    key={s.source.acceptance_id}
                  >
                    <span>Turn {short(s.source.turn_id)}</span>
                    <strong>
                      {s.relevant
                        ? "本轮也被选为 Relevant"
                        : "仅近期候选 · 未选为 Relevant"}
                    </strong>
                    <small>
                      A 分支输入 · {s.origins.join(" / ") || "未记录来源角色"}
                    </small>
                  </div>
                ))
              ) : (
                <p>本轮没有近期候选。</p>
              )
            ) : (
              <p>候选参与情况未记录 / 无法核对，不能按时间顺序推断。</p>
            )}
            <p className="context-note">
              近期先参与候选检查；仅被相关性决定选中的历史用于解释。
            </p>
          </section>
          <section className="context-card" aria-label="Working State">
            <header>
              <span className="eyebrow">WORKING STATE</span>
              <span className="context-count">
                {observed ? (context.working_state?.length ?? "—") : "—"}
              </span>
            </header>
            <h3>解释器收到的状态项</h3>
            {observed ? (
              context.working_state?.length ? (
                <ul>
                  {context.working_state.map((entry) => (
                    <li key={entry.item.id}>
                      <strong>{entry.item.key || entry.item.kind}</strong>：
                      {entry.item.value}
                      <small>
                        {context.used_state_item_ids?.includes(entry.item.id)
                          ? "本轮使用"
                          : "输入中存在 · 本轮未使用"}{" "}
                        · {short(entry.item.id)}
                      </small>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>空 · 0 个输入状态项，0 个本轮使用项。</p>
              )
            ) : (
              <p>
                输入投影未记录 / 无法核对；本轮使用项：
                {trace.input_state_item_ids?.length ?? "未记录"}。
              </p>
            )}
            <p className="context-note">
              如实显示输入状态；不从历史答案生成或补写状态。
            </p>
          </section>
        </div>
        <section
          className="context-card context-evidence"
          aria-label="Current Evidence"
        >
          <header>
            <span className="eyebrow">CURRENT EVIDENCE</span>
            <Quote size={19} />
          </header>
          <h3>本轮重新检索的文档证据</h3>
          <div className="context-evidence-stats">
            <div>
              <strong>{trace.evidence_ids?.length ?? "—"}</strong>
              <small>当前 Evidence 片段</small>
            </div>
            <div>
              <strong>{trace.scope.version_ids.length}</strong>
              <small>固定来源版本</small>
            </div>
            <div>
              <strong>{citations.length}</strong>
              <small>本轮答案引用</small>
            </div>
          </div>
          <p className="context-evidence-rule">
            History / State → 解释问题
            <br />
            Current Evidence → 支持答案
          </p>
          <div className="context-source-versions">
            {trace.documents?.map((doc) => (
              <p key={doc.document_version_id}>
                <strong>
                  {citations.find(
                    (c) => c.document_version_id === doc.document_version_id,
                  )?.filename ?? "固定文档版本"}
                </strong>
                <small>Version {doc.document_version_id}</small>
              </p>
            ))}
          </div>
          <div
            className="context-current-citations"
            aria-label="当前轮文档引用"
          >
            {citations.slice(0, 3).map((c) => (
              <blockquote key={c.label}>
                <span>
                  {c.label} · 第 {c.span.boxes[0].page_index + 1} 页
                </span>
                <p>{c.span.quote}</p>
                <small>Evidence {short(c.evidence_id)} · 当前文档原文</small>
              </blockquote>
            ))}
          </div>
          {citations.length > 3 && (
            <p className="context-note">
              展示前 3 条；共 {citations.length} 条真实当前轮引用。
            </p>
          )}
          <p className="context-note">
            引用物理校验：{trace.validation ?? "未记录"}。语义支持：
            {trace.semantic_support}。
          </p>
          <details>
            <summary>当前 Evidence / 解释身份</summary>
            <p>EvidencePack {trace.evidence_pack_identity ?? "未记录"}</p>
            <p>Interpretation {trace.interpretation_identity ?? "未记录"}</p>
            <p>候选输入 {context.candidate_input_identity ?? "未核对"}</p>
          </details>
        </section>
      </div>
      <footer className="context-observation-foot">
        只读检查 ·{" "}
        {context.availability === "VERIFIED_LOCAL_RECEIPT"
          ? "本地观察记录与不可变 Acceptance / 已发布 Trace 已核对"
          : context.availability}{" "}
        · 不触发解释、检索或模型调用
      </footer>
    </div>
  );
}

export function ContextPage() {
  const [params, setParams] = useSearchParams();
  const catalog = useQuery({
    queryKey: ["context-run-catalog"],
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/runtime/conversation-runs", {
          params: { query: { limit: 25, offset: 0 } },
        }),
      ),
  });
  const rows = catalog.data ?? [];
  const requestedRun = params.get("run");
  const row = requestedRun
    ? rows.find((r) => r.run_id === requestedRun)
    : (rows.find((r) => r.status === "ACCEPTED") ?? rows[0]);
  const load = (
    path:
      | "/v1/conversations/{conversation_id}/runs/{run_id}/inspection"
      | "/v1/conversations/{conversation_id}/runs/{run_id}/context",
  ) =>
    api.GET(path, {
      params: {
        path: { conversation_id: row!.conversation_id, run_id: row!.run_id },
      },
    });
  const inspection = useQuery({
    queryKey: ["context-inspection", row?.run_id],
    enabled: !!row,
    queryFn: async () =>
      unwrap(
        await load(
          "/v1/conversations/{conversation_id}/runs/{run_id}/inspection",
        ),
      ) as Inspection,
  });
  const context = useQuery({
    queryKey: ["context-observation", row?.run_id],
    enabled: !!row,
    queryFn: async () =>
      unwrap(
        await load("/v1/conversations/{conversation_id}/runs/{run_id}/context"),
      ) as ContextObservation,
  });
  const error = catalog.error || inspection.error || context.error;
  const siblings: Summary[] = rows
    .filter((r) => r.conversation_id === row?.conversation_id)
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  return (
    <section className="context-page">
      <div className="context-page-heading">
        <div>
          <p className="eyebrow">CONVERSATION / CONTEXT INSPECTOR</p>
          <h1>上下文与指代解析</h1>
        </div>
        <span>
          <LockKeyhole size={15} />
          只读 · 真实运行
        </span>
      </div>
      <div className="context-select">
        <label htmlFor="context-run">运行记录</label>
        <select
          id="context-run"
          value={row?.run_id ?? ""}
          onChange={(e) => setParams({ run: e.target.value })}
        >
          {rows.map((r) => (
            <option value={r.run_id} key={r.run_id}>
              {r.status} · {short(r.run_id)} · {r.question}
            </option>
          ))}
        </select>
        <Link
          to={
            row
              ? `/runtime/publication?run=${encodeURIComponent(row.run_id)}`
              : "/runtime/publication"
          }
        >
          检查一致发布 →
        </Link>
      </div>
      {error ? (
        <p role="alert" className="error">
          {message(error)}
        </p>
      ) : requestedRun && !catalog.isPending && !row ? (
        <p role="alert">
          所选 Run 不在当前可访问记录中；请从运行记录重新定位。
        </p>
      ) : !rows.length && !catalog.isPending ? (
        <p>没有可读取的运行记录。</p>
      ) : !inspection.data || !context.data ? (
        <p role="status">正在核对上下文观察与持久身份…</p>
      ) : (
        <div className="context-shell">
          <aside className="context-conversation" aria-label="当前会话运行">
            <span className="eyebrow">SAME CONVERSATION</span>
            <p className="context-conversation-id">{row?.conversation_id}</p>
            <nav>
              {siblings.map((r, i) => (
                <button
                  key={r.run_id}
                  aria-current={r.run_id === row?.run_id ? "step" : undefined}
                  onClick={() => setParams({ run: r.run_id })}
                >
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  <strong>{r.question}</strong>
                  <small>
                    {r.status} ·{" "}
                    {r.publication === "PUBLISHED" ? "已发布" : "未发布"}
                  </small>
                </button>
              ))}
            </nav>
            <div className="context-run-identity">
              <small>当前 Turn</small>
              <code>{row?.turn_id}</code>
              <small>当前 Run</small>
              <code>{row?.run_id}</code>
            </div>
          </aside>
          <ContextView value={inspection.data} context={context.data} />
        </div>
      )}
    </section>
  );
}
