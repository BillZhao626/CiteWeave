import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowDownToLine, ArrowRight, FlaskConical } from "lucide-react";
import { z } from "zod";
import "./benchmark.css";

const resultSchema = z.object({
  concurrency: z.number().int().positive(),
  attempted: z.number().int().positive(),
  successful: z.number().int().nonnegative(),
  failed: z.number().int().nonnegative(),
  p95_ms: z.number().nonnegative(),
  successful_per_second: z.number().nonnegative(),
  warmup_attempted: z.number().int().nonnegative(),
  warmup_failed: z.number().int().nonnegative(),
  repeat_p95_ms: z.array(z.number().nonnegative()),
  repeat_successful: z.array(z.number().int().nonnegative()),
  correctness_cardinality: z.boolean(),
  warmup_correct: z.boolean(),
});
const artifactSchema = z.object({
  schema_revision: z.literal("benchmark-surface-v1"),
  origin: z.literal("preserved-local-raw-measurements"),
  measurement_date: z.string(),
  contract_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  raw_archive_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  profiles: z.array(
    z.object({
      id: z.enum(["baseline", "final", "qdrant"]),
      label: z.string(),
      measured_at: z.string(),
      source_commit: z.string(),
      source_tree: z.string(),
      source_dirty: z.boolean(),
      raw_sources: z.array(z.object({ path: z.string(), sha256: z.string() })),
      results: z.array(resultSchema),
    }),
  ),
  contract: z.object({
    requests_per_repeat: z.number(),
    repeats: z.number(),
    warmup_per_repeat: z.number(),
    timeout_seconds: z.number(),
    pool: z.object({
      size: z.number(),
      overflow: z.number(),
      timeout_seconds: z.number(),
    }),
    runtime: z.object({
      workers: z.number(),
      provider_attempt_limit: z.number(),
    }),
  }),
  environment: z.object({
    os: z.string(),
    os_release: z.string(),
    logical_cpus: z.number(),
    total_memory_bytes: z.number(),
    python: z.string(),
    postgres: z.object({ server_version: z.string() }),
  }),
});
type BenchmarkArtifact = z.infer<typeof artifactSchema>;
type BenchmarkResult = z.infer<typeof resultSchema>;

async function loadBenchmark(): Promise<BenchmarkArtifact> {
  const response = await fetch("/benchmarks/conversation-v2.json");
  if (!response.ok) throw new Error("本地测量文件尚未载入");
  const parsed = artifactSchema.safeParse(await response.json());
  if (!parsed.success)
    throw new Error("测量文件格式不完整，请重新生成原始结果视图");
  for (const profile of parsed.data.profiles) {
    if (
      profile.results.some(
        (row) => row.successful + row.failed !== row.attempted,
      )
    )
      throw new Error("测量分母不一致，结果未显示");
  }
  return parsed.data;
}

const ms = (value: number) =>
  value.toLocaleString("en-US", { maximumFractionDigits: 1 });
const rps = (value: number) => value.toFixed(3);

function SuccessChart({
  before,
  after,
}: {
  before: BenchmarkResult[];
  after: BenchmarkResult[];
}) {
  return (
    <div
      className="bench-success-chart"
      role="img"
      aria-label="各并发级别优化前后成功完成次数，每级别 120 次测量"
    >
      <div className="bench-chart-scale">
        <span>0</span>
        <span>60</span>
        <span>120 次</span>
      </div>
      {before.map((base) => {
        const final = after.find((row) => row.concurrency === base.concurrency);
        if (!final) return null;
        return (
          <div
            className={`bench-success-group ${base.concurrency === 10 ? "bench-focus" : ""}`}
            key={base.concurrency}
          >
            <span className="bench-concurrency">并发 {base.concurrency}</span>
            <div className="bench-bar-pair">
              <div className="bench-bar-row">
                <span>优化前</span>
                <div className="bench-bar-track">
                  <div
                    className="bench-bar before"
                    style={{
                      width: `${(base.successful / base.attempted) * 100}%`,
                    }}
                  />
                </div>
                <strong>
                  {base.successful}
                  <small> / {base.attempted}</small>
                </strong>
              </div>
              <div className="bench-bar-row">
                <span>优化后</span>
                <div className="bench-bar-track">
                  <div
                    className="bench-bar after"
                    style={{
                      width: `${(final.successful / final.attempted) * 100}%`,
                    }}
                  />
                </div>
                <strong>
                  {final.successful}
                  <small> / {final.attempted}</small>
                </strong>
              </div>
            </div>
            <span
              className={`bench-level-note ${final.failed ? "warning" : ""}`}
            >
              {final.failed ? `${final.failed} 次失败 · 到达瓶颈` : "全部完成"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function Comparison({
  label,
  unit,
  before,
  after,
  format,
  lower,
}: {
  label: string;
  unit: string;
  before: number;
  after: number;
  format: (value: number) => string;
  lower?: boolean;
}) {
  const max = Math.max(before, after);
  const improvement = (((after - before) / before) * 100).toFixed(1);
  return (
    <div className="bench-comparison">
      <div className="bench-comparison-heading">
        <h3>{label}</h3>
        <span>{unit}</span>
      </div>
      <div className="bench-mini-row">
        <span>优化前</span>
        <i className="before" style={{ width: `${(before / max) * 62}%` }} />
        <strong>{format(before)}</strong>
      </div>
      <div className="bench-mini-row">
        <span>优化后</span>
        <i className="after" style={{ width: `${(after / max) * 62}%` }} />
        <strong>{format(after)}</strong>
      </div>
      <p className="bench-change">
        {Number(improvement) > 0 ? "+" : ""}
        {improvement}%
        <small>{lower ? "更短的工作流耗时" : "更多成功工作流"}</small>
      </p>
    </div>
  );
}

export function BenchmarkPage() {
  const benchmark = useQuery({
    queryKey: ["local-benchmark-v2"],
    queryFn: loadBenchmark,
    retry: false,
  });
  const [tab, setTab] = useState<"comparison" | "qdrant">("comparison");
  if (benchmark.isPending)
    return <main className="ops-page">正在读取本地测量…</main>;
  if (benchmark.error)
    return (
      <main className="ops-page">
        <span className="eyebrow">BENCHMARK</span>
        <h1>性能测量</h1>
        <p className="ops-intro">{benchmark.error.message}</p>
        <p className="muted">
          在项目根目录运行 python -m
          scripts.generate_benchmark_surface，以保留的原始测量生成只读视图。
        </p>
      </main>
    );
  const data = benchmark.data;
  const before = data.profiles.find((profile) => profile.id === "baseline");
  const after = data.profiles.find((profile) => profile.id === "final");
  const qdrant = data.profiles.find((profile) => profile.id === "qdrant");
  const c5Before = before?.results.find((row) => row.concurrency === 5);
  const c5After = after?.results.find((row) => row.concurrency === 5);
  const c10Before = before?.results.find((row) => row.concurrency === 10);
  const c10After = after?.results.find((row) => row.concurrency === 10);
  const c20After = after?.results.find((row) => row.concurrency === 20);
  if (
    !before ||
    !after ||
    !qdrant ||
    !c5Before ||
    !c5After ||
    !c10Before ||
    !c10After ||
    !c20After
  )
    return (
      <main className="ops-page">
        <p role="alert">对比测量不完整，结果未显示。</p>
      </main>
    );
  return (
    <main className="ops-page benchmark-page">
      <header className="bench-header">
        <div>
          <span className="eyebrow">ENGINEERING / BENCHMARK</span>
          <h1>减少数据库等待，完成更多工作流。</h1>
          <p>
            真实 HTTP + PostgreSQL 路径 · 同一固定负载 · 结果与 Trace 一起读回
          </p>
        </div>
        <span className="bench-date">
          <FlaskConical size={16} /> 本地测量 · {data.measurement_date}
        </span>
      </header>
      <div className="bench-context">
        <span>1 个 API worker</span>
        <span>
          连接池 {data.contract.pool.size} + {data.contract.pool.overflow}
        </span>
        <span>
          每级别 {data.contract.repeats} × {data.contract.requests_per_repeat}{" "}
          次测量
        </span>
        <span>每轮 {data.contract.warmup_per_repeat} 次预热</span>
        <a href="/benchmarks/conversation-v2-raw.zip" download>
          <ArrowDownToLine size={14} /> 原始结果
        </a>
      </div>
      <div className="bench-tabs" role="tablist" aria-label="测量路径">
        <button
          role="tab"
          aria-selected={tab === "comparison"}
          onClick={() => setTab("comparison")}
        >
          并发 · 优化前后
        </button>
        <button
          role="tab"
          aria-selected={tab === "qdrant"}
          onClick={() => setTab("qdrant")}
        >
          Qdrant 检索路径
        </button>
      </div>
      {tab === "comparison" ? (
        <>
          <section className="bench-chart-panel">
            <div className="bench-panel-heading">
              <div>
                <h2>成功完成 / 全部尝试</h2>
                <p>
                  失败保留在分母里；一个成功工作流包含提交、结果读取和 Trace
                  读取。
                </p>
              </div>
              <div className="bench-legend">
                <span>
                  <i className="before" /> 优化前
                </span>
                <span>
                  <i className="after" /> 优化后
                </span>
              </div>
            </div>
            <SuccessChart before={before.results} after={after.results} />
            <div className="bench-causal">
              <span>复用 Acceptance 的数据库 Session</span>
              <ArrowRight size={16} />
              <span>PostgreSQL FOR SHARE 允许并行读取</span>
              <ArrowRight size={16} />
              <strong>
                并发 10：{c10Before.successful} / {c10Before.attempted} →{" "}
                {c10After.successful} / {c10After.attempted}
              </strong>
            </div>
          </section>
          <section className="bench-comparisons">
            <div className="bench-c5-label">
              <span className="eyebrow">并发 5</span>
              <h2>
                相同成功分母，
                <br />
                观察耗时与吞吐。
              </h2>
              <p>两侧均为 120 / 120</p>
            </div>
            <Comparison
              label="p95 工作流终止耗时"
              unit="ms · 越低越好"
              before={c5Before.p95_ms}
              after={c5After.p95_ms}
              format={ms}
              lower
            />
            <Comparison
              label="成功吞吐"
              unit="workflow / s"
              before={c5Before.successful_per_second}
              after={c5After.successful_per_second}
              format={rps}
            />
          </section>
        </>
      ) : (
        <section className="bench-chart-panel">
          <div className="bench-panel-heading">
            <div>
              <h2>包含真实 Qdrant 的检索路径</h2>
              <p>Dense + BM25 HTTP 查询，包含错误版本与空间的排除检查。</p>
            </div>
            <span className="bench-date">3 个原创点 · 合成 2D 推理</span>
          </div>
          <div className="bench-qdrant-path">
            <span>FastAPI / ProductionRuntime</span>
            <ArrowRight size={18} />
            <span>Qdrant Dense + BM25</span>
            <ArrowRight size={18} />
            <span>证据验证 / Acceptance</span>
            <ArrowRight size={18} />
            <span>结果 + Trace</span>
          </div>
          <table className="bench-table">
            <thead>
              <tr>
                <th>并发</th>
                <th>成功 / 尝试</th>
                <th>p95 终止耗时</th>
                <th>成功吞吐</th>
                <th>预热失败</th>
              </tr>
            </thead>
            <tbody>
              {qdrant.results.map((row) => (
                <tr key={row.concurrency}>
                  <td>{row.concurrency}</td>
                  <td>
                    <strong>
                      {row.successful} / {row.attempted}
                    </strong>
                  </td>
                  <td>{ms(row.p95_ms)} ms</td>
                  <td>{rps(row.successful_per_second)} / s</td>
                  <td>
                    {row.warmup_failed} / {row.warmup_attempted}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <p className="bench-scope">
        测量范围：本机闭环负载，模型与 provider transport 为合成实现。p95
        含失败尝试；并发 20 优化后仍有 {c20After.failed} 次测量失败及{" "}
        {c20After.warmup_failed} 次预热失败。Qdrant 路径使用 3 个原创点、合成
        embedding / reranking。结果用于解释本次工程改进，不作为生产容量。
      </p>
      <details className="bench-details">
        <summary>查看负载、逐轮结果与来源</summary>
        <div className="bench-detail-grid">
          <div>
            <h3>负载与环境</h3>
            <p>
              {data.environment.os} {data.environment.os_release} ·{" "}
              {data.environment.logical_cpus} 逻辑 CPU ·{" "}
              {(data.environment.total_memory_bytes / 1024 ** 3).toFixed(2)} GiB
              RAM
            </p>
            <p>
              Python {data.environment.python} · PostgreSQL{" "}
              {data.environment.postgres.server_version}
            </p>
            <p>
              独立会话先接受一个未计时 seed
              Turn，再测量带有历史的当前问题。计时包括 POST + result GET + Trace
              GET。
            </p>
            <p>
              闭环调度；p95 使用 nearest-rank；吞吐以成功数除以三轮测量总时长。
              {data.contract.timeout_seconds}s 客户端 deadline；连接获取{" "}
              {data.contract.pool.timeout_seconds}s。
            </p>
          </div>
          <div>
            <h3>测量与来源</h3>
            {data.profiles.map((profile) => (
              <p key={profile.id}>
                {profile.label} ·{" "}
                {new Date(profile.measured_at).toLocaleString("zh-CN", {
                  timeZone: "Asia/Shanghai",
                  hour12: false,
                })}
                <br />
                <small>
                  历史提交 {profile.source_commit.slice(0, 8)} ·
                  文件哈希绑定实际工作树
                </small>
              </p>
            ))}
            <p className="ops-id">
              Contract SHA256: {data.contract_sha256}
              <br />
              Raw archive SHA256: {data.raw_archive_sha256}
            </p>
            <a
              className="ops-link"
              href="/benchmarks/conversation-v2.json"
              download
            >
              下载机器可读汇总与逐文件 SHA256
            </a>
          </div>
        </div>
        <table className="bench-table">
          <thead>
            <tr>
              <th>路径</th>
              <th>并发</th>
              <th>各轮成功 / 40</th>
              <th>各轮 p95 / ms</th>
              <th>预热失败 / 60</th>
            </tr>
          </thead>
          <tbody>
            {data.profiles.flatMap((profile) =>
              profile.results.map((row) => (
                <tr key={`${profile.id}-${row.concurrency}`}>
                  <td>{profile.label}</td>
                  <td>{row.concurrency}</td>
                  <td>{row.repeat_successful.join(" · ")}</td>
                  <td>{row.repeat_p95_ms.map(ms).join(" · ")}</td>
                  <td>
                    {row.warmup_failed} / {row.warmup_attempted}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </details>
    </main>
  );
}
