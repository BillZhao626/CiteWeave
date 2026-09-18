# M2 Production Core contract · v0.3 frozen (2026-09-16)

M1 v0.2 的证据坐标、source/version 身份、RRF、至少一次执行与 fenced publish 不变量保留。此规格约束 M2 新增能力；实现中如发现冲突，更新 ADR / 本规格后验证，不能暗改。

## Evaluation

数据集只由项目内固定 manifest 获取，API 不接受任意 URL / 本机路径。记录真实下载 URL、官方身份、获取日期、SHA-256、许可与分发说明。题目约 48，覆盖 direct、multi-evidence、cross-document、unanswerable、boundary、localization；dev/test 在第一次运行前按 case 固定并生成哈希。参考原文用 source hash + page + block + codepoint span 绑定。生产问答不读取 gold 或 case_id。

每次批量运行有 UUID、dataset/split/hash、实际 profile 和 Prompt hash；每题关联普通 QueryRun。保留错误题，分母不丢失。分路 Recall/MRR/nDCG 不直接跨文档混加 BM25 分数；按文档作用域和声明的合并规则输出。候选 / rerank 输入 / final evidence 的 gold 覆盖分开。

Citation grounded 必须重新解析授权 run → version → blob hash → PDF block → span/boxes。身份有效与语义支持分开。答案 correctness/completeness/faithfulness/relevancy/refusal 使用版本化评审 rubric；机器辅助评判必须标注方法与局限，人工复核记录不能由 AI 伪造。若使用 LLM judge，保留 model/config/prompt/usage 并与实际人工复核区分；未复核显示未复核。

## Trace / API / UI

扩展现有 QueryRun，不另造重复的 query 身份。记录 request/config/snapshot、阶段 start/end/latency/status/count/retry/error，以及逐次调用 usage 摘要。禁止 trace 记录凭据、完整 provider 响应或完整 Prompt；问题与引用按现有 owner 权限读取。Job 仍用持久阶段事件，补足可诊断信息。

新增已认证、作用域受限、必要时分页的 Runs / Evaluation / Versions / System API，均有 Pydantic response schema，生成 TS 类型。React 普通问答保持简单，诊断细节单独进入 Run Inspector。

## Lifecycle

索引是派生数据，原件/规范文本/历史引用不可因 rebuild 改写。rebuild 创建独立任务和物理 collection，验证完整后切换派生索引指针；引用继续解析原 immutable version。新 rebuild job 的命名不能与旧 ingestion fence 碰撞。

GC 默认 dry-run，列 candidate/protected/reason。仅处理已确认归属的 CiteWeave 索引；未知 collection 保护。保护 active/published、历史引用、运行 snapshot、有效租约、维护操作。执行前再次检查，在与 query snapshot / rollback / publish 协调的事务边界内决策；外部 delete 幂等，保留操作审计，失败不得标成功。

Rollback 是显式切换一个文档的有效 READY 版本，要求 expected active version 防丢失更新；与正在发布的任务协调。已有 run/citation 始终绑定旧版本和实际参与检索的物理索引映射。

备份保护 PostgreSQL + BlobStore，记录一致性方法和哈希。恢复到新的测试数据库/目录/派生索引环境，禁止覆盖原业务库或旧 RAGFlow。至少一次真实 dump/restore、blob 哈希、引用解析和索引重建验证。

## Reliability / resources / cost

错误分 retryable、non_retryable、cancelled、unknown_outcome。Provider / model 调用有 deadline、有界 retry 与可观测 attempt；Qdrant 查询单次 8 秒、不叠加自动 retry，摄取由持久 Job 有限重试。输出后不自动重新生成；取消关闭上游 stream；任何异常或非法 citation 不得产生 VALID FINAL。usage 即使失败也尽可能落盘，不确定费用保留预算预留。

适度 breaker 提供 closed/open/half-open 状态和恢复探测；单机资源限额保持，模型队列有上限与等待 deadline，不无限创建推理任务。以真实受控负载记录并发、延迟、失败、RAM/GPU，再决定缓存；不缓存 LLM 答案作为默认提速手段。

每 run 显示 token、input/output 估算、retry/failed 费用以及不确定部分；项目预算仍最多 ¥50，actual provider charge 无可靠接口则 unavailable。实际行为与整体证据见 `docs/reports/M2_ACCEPTANCE.md`；变更冻结不变量须更新规格和 ADR，并运行相应回归。
