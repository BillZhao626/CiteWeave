# v0.2 — Bounded Local-First Calibration Execution Plan

Status: **PROPOSED — awaiting Human Local Calibration Execution Review** · 2026-09-29

Calibration execution: **NOT AUTHORIZED** · Provider: **0 calls / 0 CNY** · 有限 CNY 授权：**NONE / PENDING** · Baseline pilot: **NOT AUTHORIZED** · Implementation: **NOT_STARTED**。

本文只申请下一次本地批次，不包含执行结果。v0.2 仍为 DESIGNED；不声称 IMPLEMENTED、VERIFIED 或 RELEASED。方法：Calibration Planning、Cost-Aware Experimental Design、Evidence-First Scope Reduction、Speed-to-Vertical-Slice Optimization、Human Execution Gate。

## 1. 已核实基线与边界

2026-09-29，起始分支 `main`，工作树干净；本地 main、origin/main、HEAD 与 `git ls-remote origin refs/heads/main` 均为 `671dfac0c5f0b56c7ef27a2c49062988c2686a64`（`docs(v0.2): accept cost-aware calibration plan (#4)`）。[Calibration Plan](V02_CONVERSATIONAL_CALIBRATION_PLAN.md) 已 ACCEPTED；Lean 是选定的最大 campaign 框架，**不是目标或执行授权**。保持 LOCAL-FIRST / PROVIDER-OFF-BY-DEFAULT 及上述全部授权状态。

唯一工程目标：

> Without breaking the v0.1 Evidence RAG contract, allow users to reliably continue a conversation while ensuring that each factual answer is re-grounded in current Evidence, the conversation has exactly one accepted truth, and failures can be localized through Trace.

即 Context + Evidence + State + Reliability + Trace。路线为 v0.1 Evidence RAG → v0.2a Conversational Evidence RAG / Stateful Conversational Backend / 最小状态一致性 → v0.2b Reliability Hardening → v0.2 Multi-turn Evaluation；Tool / Function Calling / MCP 属于后续 v0.3 方向。v0.2 不称 Agent Runtime。

**Strategic Drift Guard**：保持 Dense + BM25 + RRF + BGE + EvidencePack + Citation → Evidence → immutable source/PDF。没有证据把文档检索定位为阻塞项，因此不调查、比较、更换 embedding/retriever/vector DB/hybrid/reranker/chunking 或检索基础设施。不引入 Summary、第二套向量记忆、长期记忆、个性化、Multi-Agent、Tool Runtime、Function Calling、MCP、planner/executor 或新基础设施。

**Speed Guard**：每项观测必须改变下表中的一个决定；没有决定就延期。一次小批次取得结构边界后停止，不为填满 PENDING、M 编号或 Lean 额度补实验。不建通用评测平台或伪会话运行时。实现后的证据更强时，登记后测；不借校准实现产品。

依据为 [Feature §4–5、§7](specs/07_V02_First_Conversational_Slice.md)、[Evaluation §1–3](specs/08_V02_Conversational_Evaluation.md) 与 Calibration Plan §4–5、§8–13。**现有 Comparison Protocol Freeze 是实现前门禁，本文不将它移到实现后，也不豁免精确预算和计量要求。** 本地批次结束与实现授权是两个不同判断，见 §8。

## 2. 当前能力与 M01–M07 审计

仅定向检查当前公开代码与 fixture 许可说明：[profiles.py](../src/citeweave/profiles.py)、[context_tokens.py](../src/citeweave/context_tokens.py)、[evidence_selection.py](../src/citeweave/evidence_selection.py)、[query_evidence.py](../src/citeweave/query_evidence.py)、[answering.py](../src/citeweave/answering.py)、[llm.py](../src/citeweave/llm.py)、[原创结构 fixture](../tests/fixtures/telecom_structure/README.md)。现有 pack 有确定序列化和固定 profile；BGE 计量依赖 `/context-tokenize` 服务，不是生成 tokenizer。旧路径有 12000 content codepoints 保护和 `max_tokens=1024`，均不能充当 v0.2 预算或官方容量。没有现成多轮 manifest、selector、Context Assembler 或 Conversation 持久化测量路径；普通 PG 查询不能回答历史分支成本。本次未访问运行数据库、模型缓存、凭据或 sealed 数据。

下表每行只有一个主要可执行状态和时间分类。`EXECUTABLE_NOW` 指已有人工标注/文件计算方法可用，**不表示已有数据或已执行**。M07 按静态与运行时拆分，不能用前者替代后者。

| M / 决策 | 主可执行状态 | 唯一时间分类 | 会改变的首切片决定；最便宜有效证据 / 当前能力 | 所需证据、增量成本、停止点；真实切片是否更好 |
| --- | --- | --- | --- | --- |
| M01 → D01/D02 | EXECUTABLE_NOW | MUST_MEASURE_BEFORE_IMPLEMENTATION | 需要哪些旧来源定位条件、哪些依赖不能由 recent A 单独覆盖；人工 accepted-Turn 距离/等价组/纠正链，现有标注方法可用、材料待写。A+B 已接受，不重新投票决定是否保留 B | manifest 依赖表 + receipt 距离原值/断点；工程 10 分钟，共享 F1–F4 人审。结构分布足够支持初始边界即停；真实切片更适合测自然频率，当前只测构造的必要性 |
| M02 → D02/D05 | EXECUTABLE_NOW | SAFE_TO_START_WITH_CONSERVATIVE_BOUND | 候选应携带的来源关系、必须暴露的 cutoff 缺口；复用 M01/M03 的 reference lookup，统计 A 覆盖和仍需 B 的组。无真实 B 排名/检索实现 | receipt reference counts；可选增量 ≤5 分钟，无新增 target/人审。若不能改变字段/遗漏诊断就 skip；真实 B recall/rank/C 与 I/O 更应后测 |
| M03 → D03/D04/D06 | EXECUTABLE_NOW | MUST_MEASURE_BEFORE_IMPLEMENTATION | 来源组的不可分单位、精确去重身份、state 投影与原文的责任边界；required/optional/forbidden、supersession 图静态标注，现有方法可用 | manifest 组/边/身份 + receipt 完整组数；工程 15 分钟，共享 F1/F3/F4/F6 人审。关键关系可表示且无未决冲突即停；真实切片更适合测选择效果，不能替代先明确语义单位 |
| M04 → D03/D06/D07 | EXECUTABLE_WITH_SMALL_LOCAL_ADAPTER | SAFE_TO_START_WITH_CONSERVATIVE_BOUND | 有限输入封套、mandatory 无法装下时的边界及诊断字段；现有 pack 字符串 + 人工参考组件，只测精确 bytes/codepoints，尚无 v0.2 serializer / verified generation accounting | receipt 组件/整体计数与 hash；适配和计量合计 ≤30 分钟。无法取得合法完整 pack 则相应项 unavailable；不造 assembler。真实 framing/token reserve 留真实实现与计量门禁 |
| M05 → D07 | UNAVAILABLE_NONBLOCKING | BETTER_MEASURE_AFTER_REAL_VERTICAL_SLICE | 会改变真实输出 reserve；但单独参考答案字符数不能决定生成输出容量，生成 tokenizer/finish/usage/截断/方差当前不可得 | receipt 明确 unavailable；本批增量 0。已有参考文字可附 bytes/codepoints，不新写答案或适配器。真实输出证据更好，provider 另有 Gate；不以旧 1024 宣称安全的 v0.2 reserve |
| M06 → D02/I/O | DEFER_TO_POST_VERTICAL_SLICE | BETTER_MEASURE_AFTER_REAL_VERTICAL_SLICE | 真实历史候选的行/字节/round trips/查询期限；当前无 Conversation 查询，普通 PG probe 不能改变此决定 | receipt deferred + 未来真实查询证据需求；本批 PG/工程 0。需要 schema/查询实现即停；真实 PG 路径后测，不建假 persistence |
| M07-pre → D08/D09/硬边界 | EXECUTABLE_NOW | MUST_MEASURE_BEFORE_IMPLEMENTATION | 标签中的 self-contained/依赖/歧义区分、mandatory/scope/provenance/overflow 预期行为；已有 Feature 可逐项核对 | manifest 断言 + receipt 契约检查；工程 10 分钟，共享全部 target 人审。每个关键断言有来源/期望、争议已解决即停；这只是标签契约证据 |
| M07-runtime → 状态一致性/恢复 | DEFER_TO_POST_VERTICAL_SLICE | BETTER_MEASURE_AFTER_REAL_VERTICAL_SLICE | admission/有效接受/恢复实现选择；需要真实事务与服务，当前不存在 v0.2 路径 | receipt deferred；本批工程/运行 0。幂等、fingerprint、expected head、single active Turn、fencing、accepted 唯一、cancel/final race、事务原子性、SSE disconnect、restart reconciliation、stale rejection 全留实现测试，静态/mock 不记 VERIFIED |

M01/M03/M07-pre 的 MUST 仅指最低限度的人审结构证据，避免不完整来源单位或错误依赖责任进入首版；不是测质量率。M05 不选 SAFE 的理由是当前无法论证正数的真实输出容量；用任意字符或旧输出值代替会违反 assembler 契约。其缺失不阻塞本地批次，但真实生成仍受计量与授权门禁约束。

SAFE 的具体保守起点（均为待接受的初始工程提议，非调优值）：

- M02：模糊/语义去重合并次数 **0**，自动 refetch/模型修复次数 **0**；相同原始身份可合并引用但保留所有来源关系。显式来源与 mandatory 无法完整恢复就澄清/失败并记录缺口，不把缺口伪称召回。真实切片出现可恢复 miss 或重复负担时重评；N/C/K 的精确值仍须另行冻结。
- M04：建议首版输入的额外传输保护上限为 **65536 UTF-8 bytes / 完整序列化输入**，解释与生成分别检查；这只是有限内存/封套保护，不是模型容量。mandatory + 完整 pack 超界则明确失败，不截 pack/否定。生成 `ready` 还必须通过已接受的 `tokens(full messages) ≤ min(input cap, model context − output reserve)`；计量/容量/reserve 未验证时派发上限 **0**、fail closed。真实 serializer、较大完整 pack/mandatory、语言/模型变化触发重评。若本批完整必要输入已超此界，报告该提议不可行，停止而不扩界。

## 3. 唯一推荐批次：6 个族，10 个 target views

Phase A：一个原创 Calibration manifest，以下六个不同实体/任务/模板/来源族，共十个目标视图；同族配对不算独立样本。每族最多 16 个 accepted 历史 Turns，每族仅一个材料包；全部 Calibration split，不读取或创建 Development、Regression、sealed confirmation。AI 辅助草稿标 provisional，关键标签经 owner 复核后才称 human-reviewed。历史是人工参考前缀，不是真实 accepted 运行结果。

| 族 / views | 为什么独立存在；覆盖 | 改变的设计输入 / 可暴露的失败 |
| --- | --- | --- |
| F1 / 1 | 唯一实体的指代 + 省略 + simple follow-up，包含明确否定约束 | 最低必要原文与补全 provenance；暴露补错实体、只留答案不留原文 |
| F2 / 2 | 自足新题与 topic shift 的对照，含空历史参考视图 | self-contained/skip 边界、topic-local 与仍适用的会话约束；暴露新题污染。空历史仅契约参考，不声称单轮回归已通过 |
| F3 / 2 | old-but-relevant / new noise 配对，其中返回旧 topic | accepted 距离和 B 所需旧来源定位、返回时仍使用当前 head；暴露 recency 挤掉相关信息或回滚状态 |
| F4 / 2 | correction / supersession 前后两视图，同文字不同身份/版本 | 完整纠正链、active 与 superseded、精确去重身份；暴露语义组被截断或旧条件复活 |
| F5 / 1 | 两个同等适用实体的 ambiguous reference | unresolved/澄清最小信息；暴露凭最近实体猜答，不能由 F1 的唯一指代证明 |
| F6 / 2 | 否定/version/time + 本轮 scope 收缩配对，后者无足够当前 Evidence；在同一 payload 上核对容量边界 | Rewrite 禁变断言、历史不升级 Evidence、mandatory + 完整 pack；暴露 scope 扩张、旧答案充证据、把 overflow 误称证据不足 |

六族是六种不能互相代替的责任边界，十 views 来自四组必要对照加两个单视图，不为凑整扩样。F3 距离按实际前缀计算；不增加噪声只为拉长尾部。F6 容量边界是对相同完整 payload 长度 `L-1 / L / L+1` 的静态不等式核对，不增加三组产品运行或调用，不伪装为产品 overflow 测试。

Phase B（必做）：M01、M03、M04 可执行字节/码点部分、M07-pre。Phase C 只有一个允许项：M02 的标签/reference lookup，复用同一份输入、≤5 分钟且能改变来源字段或 cutoff 诊断时执行；否则带理由 skip。M05/M06 不纳入批次，M07-runtime 延期。不得追加族、views、候选 arms、模型调用或重复运行来补空字段。

覆盖登记必须逐项映射 Evaluation §3 的十八类别：F1 对应 simple/pronoun/omitted/rewrite-required，F2 对应 shift/no-rewrite/单轮契约，F3 对应 old/noise/return，F4 对应 correction/supersession，F5 对应 ambiguity，F6 对应 rewrite-danger/scope/evidence-insufficient/pressure。boundary supplement 的 provenance/禁止历史假设作为各族正交断言，真实故障另记 post-slice。七 hard 层 old/noise/return/correction/ambiguity/negation/pressure 均有标注入口；“有入口”不等于质量覆盖或运行时验证。若实际写作无法形成独立族或关键标签覆盖，保留不足并停止，不拆同族虚增样本或跨 split。

## 4. 测量方法与唯一小适配器

只提议下一授权执行时创建一个标准库文件 `scripts/measure_v02_local_calibration.py`，读取显式指定的 manifest，校验/计数/散列并输出单一 receipt；创建与调试 ≤20 工程分钟。它复用已接受的来源类型和组件边界，**不定义产品 DTO、prompt、selector、state 更新或 assembler 决策**。不导入会初始化 settings/provider/DB 的产品入口，不联网、不启动服务、不下载 tokenizer、不修改 fixture 或 pack。

| 测量 | 固定方法与限制 |
| --- | --- |
| M01 | head 是 accepted 序列末尾；令 target 序号为 head 序号 + 1，距离为 target 序号减 source accepted 序号（最近来源距离 1），pending/failed/cancelled 不进分母。每 target 记录 required 等价组的允许来源距离及纠正链，不任选较近来源隐藏链；保留原值，按族报告 min/median/max、ECDF，十 targets 不能推断总体尾部 |
| M02（可选） | 仅以标注的允许来源表计算 recent 窗口在观测距离断点的组覆盖，以及其余所需旧组；报告合格来源/组数量与截断后的缺口。显式 reference 顺序不能称 B rank、B recall、AB0 或胜者；没有真实分支的 depth/cutoff 记 unavailable |
| M03 | required 组间全需、组内仅允许已标注等价替代；纠正链保留边与原文 span。身份含 conversation/head/Turn/Run/source type/span/hash，另保留 scope/doc-version 与 supersession 关系；相同文本不能合并不同身份/否定/版本。分别记录 mandatory 原文、state 必要投影、可选/禁止项，不能以投影删除持久 snapshot |
| M04 | 固定测量封套版本：UTF-8、LF、JSON `ensure_ascii=False, sort_keys=True, separators=(",", ":")`；组件为 original query、constraints、带 provenance 的 state 投影、人工选定完整 history groups、完整参考 EvidencePack、现有模板原文与参考 message framing。解释/生成封套分开。对原字符串、组件编码及整体编码分别计算 UTF-8 bytes / Unicode codepoints / SHA256；JSON 转义、标签、分隔符与封套增量单列。该封套是测量表示，不冻结最终产品排序/prompt；真实 v0.2 message framing 和 generation tokens 记 unavailable。未来有 verified tokenizer 才可计 full tokens，不能累加片段 token 或从 BGE/字符换算 |
| M07-pre | 核对每项 provenance/scope/head、纠正图、mandatory、self-contained/歧义、禁止假设与 expected outcome；哈希/引用存在性等机器检查只证明记录一致。人审判断标签语义。注入历史、旧答案、失败草稿均不作为 Evidence。容量示例只证明标注边界，不证明实际无调用/无提交 |

原创参考 pack 按当前公开结构/许可边界制作，明确标为 reference payload、非本轮检索结果；保留完整 span/版本/范围元数据，不声称已通过 BGE pack 预算或真实 Citation→PDF 路径。不能在预算内构造合格 payload 就记 unavailable；不得运行摄取/检索来补齐。已有模板仅按显式公开路径读取并记录 hash，绝不编辑。生成 tokenizer、官方 message accounting/容量、finish/usage、随机方差、真实 generation 截断全部 PENDING；本地计量不掩盖这些缺口。

## 5. 下一执行的最小产物与可追溯性

下一次获授权才创建 `.artifacts/v02-calibration/local-first-01/` 中四个文件；本次不创建目录或数据。保持该目录已被忽略，默认不公开原始材料。将 accepted Plan §12 的逻辑产物合并为以下物理文件，不丢其适用字段：

| 文件 | 合并内容 |
| --- | --- |
| `manifest.json` | manifest + dataset + coverage + review：六族/十 views 的原文、来源/许可/作者/AI 标志、scope/immutable 版本/span、required/optional/forbidden/纠正图、critical/十八类别/七 hard 映射、reviewer/事件/时间/争议与标签状态。每个原始组件可恢复，不仅留 hash |
| `local-receipt.json` | local-measurements + accounting + candidate-ranges + budget-ledger/proposal + baseline-pilot skip：M ID/target/source-group、精确输入/封套 hash、原值/缺失/推导规则、各维预算实际使用、provider=0、pilot 未授权、所有 deferred/unavailable。无真实候选结果或数据库性能值 |
| `report.md` | 唯一合并总结：每项决定 → manifest ID → receipt 字段路径；保守界/断点/不可行项、六族限制、完成/未完成退出项、下一 Human Gate。不另建逐 M 报告 |
| `receipts-index.json` | 上述三文件及适配器/公开输入 SHA256、接受的计划 commit、基线 tree、Python/OS/CPU 身份、时刻/耗时/失败/skip；index 自身 hash 写入执行交付信息，避免自引用。环境仅 allowlist，不记录 env dump/密钥/完整 DB URL |

四文件上限合计 4 MiB。本地原始证据的地址和权限足以让 owner 复算；任何 hash mismatch 阻断引用。允许公开的仅为 owner 复核后显式列出的派生摘要/原创许可材料，不能自动把 `.artifacts/` 或原始日志提交。新小脚本将是下一执行任务的唯一计量入口，不是本次修改。

## 6. 精确子预算与零 provider 合约

唯一申请的 CAL 子账为 `local-first-01`，包含全部阶段与可选 M02；不借 DEV/HARD/REG/RES，不使用 Lean 剩余额度自动扩张。

| 资源 | 硬上限及分配 |
| --- | --- |
| 活跃执行总 elapsed | **240 分钟**，从 owner 指定启动时刻计至收据封存，等待/暂停/恢复均计入；到期停止。同一连续工作块，不跨多日继续旧授权 |
| 工程 | **120 分钟**：setup 10、材料/标注草稿 25、M01 10、M03 15、适配器 20、M04 计量 10、M07-pre 10、可选 M02 5、报告/恢复 15。恢复 ≤10 分钟且包含在最后 15 分钟内；无未分配追加工时 |
| Human review | **12 units / 96 分钟**，任一先到即停：十个 target 各完整复核一次，最多两个争议/复核事件；每 unit 预留 8 分钟。所有 critical 标签和失败均须复核，不能抽样代替。第 11/12 次不是增加 target；未完成 mandatory review 时不宣告成功 |
| Local compute | **15 分钟进程 wall / 900 CPU-seconds / 峰值 RSS 512 MiB**；一个串行进程，无 GPU、PG、容器或云资源。manifest ≤1 MiB、所有输入合计 ≤2 MiB，最多 6×16 个历史 Turns、10 views、每 view 参考封套 ≤65536 bytes。超界保留错误收据，不能截语义组 |
| 执行次数 | 同一固定 manifest **1 次**静态测量，无 arms/repeats/cold-warm。适配器输入校验失败也占次数；修复需在报告说明并重新请求授权，不自动重跑。适配器开发只用微型格式/Unicode检查，不生成额外场景 |
| Provider / 支出 | **0 次物理发送 / 0 CNY**；generation、Rewrite、Judge、DeepSeek、baseline pilot、账单查询全部 0；付费适配器与 RES 使用量 0；cloud rental 0。本地电力成本未计量，不能声称全部机器成本为零 |

工程 + 人审 + 机器时间即使全串行仍 ≤231 分钟，余 9 分钟仅总 elapsed 缓冲，不增加任何子账。每一步先检查剩余工时与 mandatory review 容量；计量进程由外层限时并记录 CPU/RSS，资源限制无法建立时不启动。上限比 Lean CAL 的 4 工程小时、32 review units、60 机器分钟更小。达到任一上限交付 PARTIAL/INCONCLUSIVE 与具体缺口，不自动扩族、加调用、重试、延期或释放 RES。

## 7. 可推导内容、未冻结值与停止规则

允许：构造集的依赖距离分布、A 窗口外仍需旧来源的证据、required 组数/完整组大小、去重身份约束、state/history 责任边界、序列化大小、硬约束下不可行区域、少量候选范围/断点、参考输入相同的配置折叠、保守起点。

沿 accepted Plan §5 的 L/P/H 法提出每参数最多三个有证据的不同点；没有真实计量或成本横轴就只报观测断点/PENDING，不伪造 P/H。每个断点必须回链原 target/group/计数字段，reference input 相同只代表该封套相同，不代表运行时等效。按 critical 完整性先过滤，不用总体平均掩盖关键缺口。没有自然会话质量估计、统计泛化或实验 winner。

**仍 UNFROZEN**：最终 N/C/K、selector、Rewrite 策略、state/history/input/interpretation token caps、context-token budget、output reserve、候选 I/O、产品 deadlines/retry/会话总额、latency target、quality/noninferiority/material-similarity thresholds、repeats、比较 arms。上述临时 byte 保护与零自动扩展策略不是最终优化值或 Comparison 签署。

停止并分类/延期：观测无法改变决定；需要 provider、产品行为、新 schema/migration/服务或大量 harness；实际切片可提供更好的证据；批次将超单工作块；材料许可/身份不明；hash 不匹配；mandatory 关系/标签争议未决。发现与已接受 Feature/Evaluation/ADR 的真实矛盾时停止并报告，不改已接受文本。如果必须扩大范围才可解决安全结构缺口，标 **BLOCKING_REQUIRES_HUMAN_DECISION**，只列该具体缺口，不泛称继续调查。

## 8. Local Calibration Exit Criteria 与后续门禁

本批同时满足以下条件就结束前置本地校准，不因 provider/PG/运行时字段 PENDING 继续采样：

1. 已人审的十 views 无未决硬不变量冲突，全部来源/许可/hash 可追溯。
2. 依赖和旧来源证据足以描述初始 A+B 所需行为，缺失来源/截断必须可见。
3. correction/supersession/mandatory/forbidden、state 与原文责任已明确。
4. 有限输入封套可用测量或保守保护实现；不以 bytes 冒充 tokens，完整 mandatory/pack 超界可明确失败，真实生成计量仍 fail closed。
5. provider-specific 项标为对本批非阻塞、对真实生成单独 gated；没有伪造输出容量。
6. 余下未知项均回链到真实切片/可靠性测试或独立 provider Gate，其证据价值高于继续静态扩样。
7. 没有尚需前置本地测量才能解决的具体结构风险；所有必须 review 已完成，预算完整结算。

结论分开填写：本地批次可记 **LOCAL BATCH DONE / CAL PARTIAL / Comparison BLOCKED**，与 accepted Plan §12 保持一致。设计边界明确不等于真实能力 VERIFIED。

**“After this local batch succeeds, can v0.2a Vertical Slice implementation start?” — NO：唯一当前阻塞是已接受的实现前 Comparison Protocol Freeze Human Gate 尚未完成（Feature §7 / Evaluation §1）。** 本文没有将其降为仅比较前门禁。可以推荐把 v0.2a 作为下一工程实现目标，但先提交该门禁所需的冻结/实现授权；这不是继续扩大本地 Calibration 的理由。provider/精确计量等缺项是否能以有依据的有限保守边界关闭，由该既有 Gate 接受；本批不宣称已关闭。如果 owner 希望先实现再补冻结，须独立审阅对已接受顺序的变更，当前授权请求不包含它。

## 9. 给 Product Owner 的唯一执行授权请求

> 授权按本文件接受的 commit 执行一次 `local-first-01`：仅六个指定原创场景族、十个 target views；Phase B 的 M01/M03/M04 字节与码点计量/M07-pre，以及最多五分钟且能改变决定的 M02 reference lookup。允许一个标准库计量脚本和四个本地受控产物；elapsed ≤240 分钟、工程 ≤120 分钟、人审 ≤12 units/96 分钟、local compute ≤15 分钟/900 CPU-seconds/512 MiB，遵守输入/文件大小与一次测量上限。Provider 0 calls / 0 CNY，不实现产品、不运行 PG、不更改已接受语义、不动用 RES。到退出条件或任一上限立即结束，交付收据和报告后停止。

Owner 只需接受/拒绝该批次，并在接受记录中填写审阅 commit、reviewer、日期和启动时刻；若批准时缺启动时刻，执行仍不开始。没有多档套餐选择。唯一另外的 owner 决定是之后的实现前 Comparison Protocol Freeze/实现授权，**不捆绑在本次接受中**。本提案接受、merge 或 CI 均不会自动执行。

本次文档发布 allowlist：本文、[HANDOFF](../HANDOFF.md)、[文档地图](README.md)、[AGENTS](../AGENTS.md) 的当前导航。无需 ADR/迁移：未改架构。只创建 Draft PR，等现有 Windows/Linux CI 到一次终态；不 merge/tag/release，不执行校准/provider/产品，不等待人工审阅。
