# v0.2 Conversational RAG — Cost-Aware Calibration Plan

Status: **PROPOSED — awaiting Human Calibration Plan Review** · 2026-09-29

Implementation: **NOT_STARTED** · 本次规划 provider calls / spend = **0 / 0**。

本文冻结的是供审阅的计划版本，不是 AI 宣告人工接受。方法为 Evaluation-Driven Development、Cost-Aware Experimental Design、Controlled Ablation Planning、Human Evaluation Gate。没有测量结果、候选胜者或已选择的 N/C/K。接受本计划后仍须另行授权有界校准执行；候选比较另经 Comparison Protocol Freeze；产品实现另行授权。

## 1. 起点、依据与文档归属

2026-09-29 经 `git fetch origin` 核实：本地 main / origin/main / HEAD 均为 `7e5b952b2effc32bfa096dfd5297354a0dda5893`，工作树干净；[PR #3](https://github.com/BillZhao626/CiteWeave/pull/3) 已于 2026-09-28T14:06:27Z 合并。Feature 与 ADR 0006–0009 已接受，Evaluation 仅方法论已接受、执行未冻结；HANDOFF 授权下一规划阶段为 Calibration Plan Freeze。AGENTS 旧导航中“尚未接受”的状态落后于这些接受记录，本次仅同步导航。

契约来源：[Feature](specs/07_V02_First_Conversational_Slice.md)、[Evaluation](specs/08_V02_Conversational_Evaluation.md)、[架构](V02_CONVERSATIONAL_RAG_ARCHITECTURE.md)、[ADR 0006](adr/0006-conversation-state-and-effective-commit.md) / [0007](adr/0007-memory-and-documentary-evidence.md) / [0008](adr/0008-bounded-conversational-context.md) / [0009](adr/0009-conversation-profile-and-trace.md)。不改变其行为、分母、S 选择规则或零容忍边界。工程与人工门禁遵循 [Playbook](AI_DEVELOPMENT_PLAYBOOK.md) 和 [Governance](ENGINEERING_GOVERNANCE.md)。

文档审计发现已有 `docs/M1_PLAN.md`、`docs/M2_PLAN.md` 平铺 Plan 命名；沿用一个 `docs/V02_CONVERSATIONAL_CALIBRATION_PLAN.md`，不新建 plans 层级，不向 Feature 塞入一次性预算。长期方法论仍归 Evaluation，实测决策须回链其 decision record。

仅检查当前公开源码/fixture 元数据和接受文档；不读私人历史审计、sealed 内容、凭据或运行数据库。没有创建数据集、harness、schema、迁移或产品代码，没有运行本地校准或 provider 实验，也不操作旧 RAGFlow 资源。

### 1.1 当前可用证据与缺口

| 当前证据（仅源码/已接受记录） | 对计划的约束 |
| --- | --- |
| [profiles.py](../src/citeweave/profiles.py)、Evaluation §2：structural pack ≤2048 BGE proxy tokens / 6400 字符 / 96 spans；seed ≤1024 proxy tokens / 3200 字符 / 64 spans | 完整 pack 固定；这是旧 profile 边界，不能等同生成 tokenizer 或会话输入预算 |
| [context_tokens.py](../src/citeweave/context_tokens.py) 通过 `/context-tokenize` 检查 BGE 身份/hash | 已有 pack 计量概念；缺所选生成模型 full-message/framing 的可验证计量，不能凭字符倍数换算 |
| [answering.py](../src/citeweave/answering.py)、[llm.py](../src/citeweave/llm.py)：旧 structural content 12000 codepoints、generation stage 35s、请求 max_tokens=1024、网络 timeout 25s | 只冻结旧 baseline 控制点，不当作 provider 官方 context window 或 v0.2 SLO |
| [settings.py](../src/citeweave/settings.py)：deepseek-flash；月预算默认/最大 50 元；query deadline 默认 60s；provider_attempts 默认 2；[judge.py](../src/citeweave/evaluation/judge.py) Judge timeout 45s | 源码不是现场设置；未来实验须显式限制每次真实发送，不能把一次逻辑调用当作一次计费；串行起步，无自动 UNKNOWN 重发 |
| answering / Judge 共享 PG advisory lock，累计 query/Judge estimated 或 reserved；准入保留 0.10 元；[costs.py](../src/citeweave/costs.py) 为 `deepseek-flash-CNY-2026-09-13` 估算 | 保留现有全局控制，但它不具备本文完整 campaign 层级，也未证明 0.10 元覆盖多阶段最坏费用；新上界不可直接套用该保留值 |
| Evaluation §2 记录公开单轮集 dev=32、regression=24、safety=16、hash；原创 [结构 fixture](../tests/fixtures/telecom_structure/README.md) / [一致性 fixture](../tests/fixtures/answer_consistency/README.md) | 只借结构/许可，不继承样本量；没有可用的多轮距离、state/history 分布；已暴露旧 regression 只作兼容守门 |
| 当前 comparison/metrics 有配对与引用检查概念，尚无多轮实现 | 不能宣称已具备会话 PG 并发证明、真实 assembler、闭环 rollout 或 campaign 预算执行器 |

当前官方模型规格、可固定 revision、价格、cache/时段/其他计费项目和真正生成 tokenizer **PENDING**。本计划不查询账单或模型服务，不用旧代码价格计算人民币结论。未来支付授权必须附官方文档 URL、访问日期、适用地区/币种/税费/生效日期及保存内容 hash；若 alias 不可固定 revision，明确 reproducibility 限制，由 owner 决定是否可接受，不能伪造 revision。

## 2. 三个边界与必须解锁的决定

1. **本次 Plan Review**：接受测量方法、覆盖和资源上限提案；选择 tier，决定是否允许单独 baseline-only pilot。当前一律不能执行。
2. **未来 Calibration execution**：仅采集标签分布、确定性计量、单一固定 baseline 的 usage/方差（若明确授权），提出少量范围。不能用候选最终答案作选择，不能在此实现会话 runtime。非现成能力记 unavailable；只能在另行授权的小型计量适配器预算内补齐。
3. **Comparison Protocol Freeze → 另行实现/比较授权**：填齐数值与身份后才做 L1 产品正确性、L2 候选 proxy 淘汰、L3–L5 真实候选比较。L0 标注分布可推导不可行范围，不能冒称某 selector 已赢。需要真实会话 PG 的验证须等已授权实现，不把它设成实施前校准的循环依赖。

决策登记见下一表。`Dxx` 与 `Ex` 是同一决策的索引；不是十二个必跑实验。每一实验启动单还须填：决策当前阻塞项、可改变选择的结果分支、最便宜证据、receipt 需求、VOI、stage/experiment/arm 分账、最大成本向量、停止条件。填不出可改变的选择则取消实验。

## 3. E1–E12：最便宜证据、分支与激活

表内 `CAL/DEV/HARD/REG/RES` 预算来自 §7–9。单项费用上限为其预先分配子账与全部父账余额的最小值；默认未分配即 **0**。E1–E10 共享同一已生成 receipt 时只计费一次，禁止每个 E 重跑整套。所有行继承 §10 停止规则。

| 决策 ID / 问题 | 最便宜有效证据与类别 | 结果 → 会改变的工程选择；升级条件 | VOI / 最大授权成本 / 特定停止点 |
| --- | --- | --- | --- |
| D01 / E1 来源贡献 | deterministic/local first：人工 required groups 对 A、B、union 的候选覆盖；R/A 为诊断 | 若 A/state 已覆盖则不重复 paid 对照；旧源只有 B 可回收则保留该分支；B 仍 miss 则定位元数据/词法缺口。R/A 不能成为违反 A+B 的胜者；只有未解决下游影响才用 Dev 输出 | HIGH；CAL 分布、DEV 子账；覆盖无差别且输入相同停止重复 arm |
| D02 / E2 N/C | local first：距离/分支候选排名、union cutoff、行/字节/PG 时间 | 截断遗漏 → 提出下一覆盖断点；增大仅添噪声/I/O → 不扩；查询不可完成 → 保留 search_incomplete 并收缩可行空间 | HIGH；CAL/DEV；超过 I/O 或同覆盖平台即停止扩档 |
| D03 / E3 K/history | local → proxy：完整必要来源组数量与全序列化 tokens、retention/intrusion | 容量不足 → 下一完整组断点；相同输入 → 合并配置；多内容可能改善答案且无代理反证 → 少量 E2E | HIGH；CAL/DEV，必要时 HARD；不能保留 mandatory 或成本支配即停 |
| D04 / E4 dedup | local first：身份/否定/scope/version/supersession 关系及重复 token 差 | 合并保真且省 tokens → 进入候选；不省 → 保留 exact ID；关系丢失 → 淘汰。纯字节相同不需要生成证明 | HIGH 的边界核验；后续美化 MEDIUM；CAL/DEV；provenance 损失停 arm |
| D05 / E5 分支/排序 | local → proxy：同候选池 source coverage、intrusion、PG I/O | 词法补漏 → 保留候选；只增噪声 → 淘汰；规则/相关层内 tie-break 产生实质不同输入才考虑 E2E | HIGH；CAL/DEV；recency 越过 relevance 硬过滤、同输入或支配即停 |
| D06 / E6 state/history | local first：mandatory 保留、state 投影、overflow | 去冗余 state 与 optional history 的结果相同 → 不建两 paid arms；有不同必要覆盖/可选信息 → 留小型比较 | HIGH；CAL/DEV；任意 necessary 断裂停；只剩可用性微调为 MEDIUM |
| D07 / E7 input/output | local 范围后 provider E2E required：参考长度、固定 baseline finish/usage，随后比较 completeness/latency | baseline 截断 → 论证 reserve 可行档；余量不能容完整 pack → overflow；幸存档答案差异可改变 reserve/input 选择才付费 | HIGH；CAL baseline-only + DEV/HARD 子账；无官方容量/真实计量先阻断，不为此盲发请求 |
| D08 / E8 overflow | deterministic/local first：相同 mandatory 超界，fake provider 调用数/accepted state | 错误调用/提交 → 修正正确性并形成新版本；合规 → 保留简单失败；提示顺序仅用户脚本恢复确有问题时另测 | HIGH 的不变量、MEDIUM 的 UX；CAL 静态 / DEV 正确性，默认 paid=0；无交互证据不升级 |
| D09 / E9 interpretation 激活 | local skip path → semantic proxy/provider：自足/依赖标签、false skip/invoke | 确定 skip 正确 → 节省调用；漏依赖 → 更保守判据；总是解释仅诊断不能取消已接受 skip。语义误差的答案后果不明才 E2E | HIGH；DEV/HARD；critical 漂移停，已有证据足以决定不加调用 |
| D10 / E10 Rewrite | structural guards → provider 语义 proxy → 必要的 E2E | 否定/entity/version/time/scope 结构破坏先排除；通过不等于语义等价；改写确能改善检索且保真 → 保留，安全原文同效 → 不改写；无法独立检索不能假 fallback | HIGH；DEV/HARD；关键漂移停，不用更多样本冲淡 |
| D11 / E11 separated interpretation | DEFERRED：先复用 combined Bad Cases、oracle 诊断定位 | 仅明确合并职责瓶颈且小适配可区分原因，才提 separated 新 Gate；否则不引入新 phases/恢复状态 | 当前 LOW，触发后须论证 HIGH；当前调用/工程额度=0；未经新 Feature/ADR 影响审阅不进入候选 |
| D12 / E12 refetch/repair | DEFERRED：本地重放证明 miss 可由有界补取恢复且下游确实需要 | 无可恢复 miss → no-refetch；可恢复 → 单独 PG refetch 提案；模型 repair 是另一个 Gate，不能随 PG 补取夹带 | 当前 LOW，阻塞决定时再评 HIGH；当前增量额度=0；UNKNOWN、歧义未解、循环风险立即停 |

与任务建议分类无分歧。HIGH 表示可能直接改变首切片决定，不等于必须支付；每行均先走最便宜层。MEDIUM 只有剩余额度且 owner 确认价值，或确实阻塞已授权决定时才排入预登记子账；不能挪用他 stage。LOW、vector Memory、Summary、模型修复循环不进入初始计划。

## 4. Calibration 采样与零 provider 测量

### 4.1 材料与独立性

使用原创或许可已核对的小技术材料及公开 fixture；记录许可/作者/AI-assisted 标识。以 entity/task/template/source 连通分组划分 Calibration、Development（screening/hard）、Regression，later-release confirmation 单独保管。跨 noise/old 配对、复述、纠正衍生保持同 split。材料不够独立时缩小结论，不拆同族虚增 n。

三档 CAL 设计为 **8 / 12 / 18 个独立族容量**，每族最多两个配对 target views，即 **16 / 24 / 36 个 target**；这是未来采样提案，不是已有样本量。Lean 的八个覆盖块为：指代/省略、自足/shift、old/noise、return、correction/supersession、ambiguity、rewrite/negation、scope/evidence/pressure。每块可多标签，必须再用 Evaluation §3 全部十八类别逐项检查；单轮兼容与 boundary 故障可作为正交本地核验。Recommended 增加实体/任务/来源差异以降低一个族包办多个风险的依赖；Ceiling 最多十八族以允许更细覆盖，仍不声称“一类一族”就是统计独立。

先登记各族 risk/source/语言/符号、accepted-Turn 距离、噪声、同 topic 实体、纠正链、single/compare pack 和答案长度的层次；target 文字/标签须在任何候选结果前固定。每 tier 的容量不能覆盖所有关键风险时，应报告不足并缩小决策范围或申请新 Gate，不能降低关键覆盖要求。本次不生成这些材料。

### 4.2 测量登记（CAL，不选择 winner）

| Receipt / 决策 | 零 provider 第一测量 | 观测与限制 |
| --- | --- | --- |
| M01 → D01/D02 | 人工标记 head 下必要原始来源、等价组、accepted-Turn 距离、supersession 链 | 每族距离 ECDF、min/median/尾部/max 与 critical 分层；pending/failed 不计历史距离 |
| M02 → D02/D05 | 预声明 reference lookup 的 A/B 每分支合格数量、必要组出现位置、union 去重前后、cutoff | search_incomplete、未找到组单列；不偷偷把 reference lookup 当已实现 AB0；无现成 selector 时只测标签所需池大小 |
| M03 → D03/D04/D06 | required/optional/forbidden 来源组数、重复内容/不同身份、state 必要/冗余条目、纠正完整组 | 序列化前后 bytes/codepoints，去重节省与关系完整性；不能合并不同 scope/version |
| M04 → D03/D06/D07 | 对固定 serializer 草案和现有 prompt/pack 做组件及 full-message 计量 | prompt、query、state、history、pack、labels/JSON escaping/message framing 和组合总数；总数不可简单用各片段 token 相加，记录交界差额 |
| M05 → D07 | 人工参考答案/澄清长度，生成 tokenizer/官方 accounting 的离线计量 | 模型/tokenizer/revision/hash、语言/符号与长短层；BGE proxy、字符、真实 tokens 分列；不可用则 unavailable，不猜 context 余量 |
| M06 → D02/I/O | 在另行允许的小型测量适配器及隔离 PG 中重放相同材料，记录分支、rows examined/returned、bytes、round trips、query time/timeout | 预声明 cold/warm、PG/version/hardware、query plan；返回 C 行不代表只扫描 C 行。缺产品查询仅证明探针成本，实际查询须 L1 再验 |
| M07 → D08/D09/硬门禁 | 标签与契约表核查 scope/provenance、duplicate/supersession、self-contained skip、mandatory overflow | fake-provider/真实产品路径的无调用、fencing/accepted 唯一须留到授权实现后的 L1；模拟不证明真实 PG 事务 |

每个 M 只执行一次已登记分层批次；重复仅用于预登记的 cold/warm 计时或基线方差。全部受 CAL 本地/工程/人审预算；不能为“零元”无限扫库。尾部与每个关键样本逐项报告，小样本分位只作描述，不声称总体 p99。新的 serializer/prompt/model/source 分布改变使相关计量失效，重新有界授权。

### 4.3 可选 baseline-only provider pilot

只有官方身份/计量、固定输入、费用上界和持久预算准入均具备后，另行明确授权。每档至多选 **4 / 6 / 9 个固定 Calibration target，各两次相同输入**，因此 8 / 12 / 18 次物理调用。选择覆盖短/长、single/compare、自足/语义依赖可用输入，不能挑候选表现差的题临时补测。第二次只估 baseline 不稳定性；不默认三次以上，不运行候选多臂。

优先复用现有 V0 `telecom-structural-v1` 的固定 generation 请求，output=1024，只测此 baseline 的使用量、finish reason、截断与时延；参考多轮 serializer 的 token 数可以离线测，不能因此声称测到会话端到端延迟。若某语义解释 baseline 尚不存在，记缺口，不能写产品 runtime 来完成 pilot；确需直接请求的单一测量适配须另行登记 prompt/契约、工程工时与 owner 许可，且取代既有 pilot slots，不加总额。校准不跑 paid Judge，人工审核 rubric 与 critical；不能混两个 baseline 的方差。

输出每项原始 usage/latency/censoring、两次差值与 rubric 变化。少量重复只决定“是否需要更多方差证据”，不能证明 deterministic。若不支付，D07 的语义完整性与 stochastic variance 保持 PENDING；本地范围证据仍可交付，不能假称 Comparison 所需证据齐全。

## 5. 候选范围推导：少量行为断点

所有数值仍 **UNSELECTED**。以下是预声明推导法，不运行密集整数网格。以每个 target 的必要组/精确序列化为依据形成覆盖阶梯；过滤硬不变量与资源不可行点，折叠产生相同实际输入与相同行为的配置。

共同取点规则：从观测阶梯取 **L：最小满足预登记必要覆盖的可行断点**；**P：按归一化资源横轴/覆盖纵轴距首尾连线最大垂距的拐点**（同距取低成本，平线无 P）；**H：owner 资源边界内最后一个仍增加必要覆盖或可辨别输入的断点**。若 L 不存在，报 INFEASIBLE；如 P/H 与 L 重合则不补造值。先按 critical 完整性，再看 ordinary 描述覆盖，不能用平均掩盖 critical miss。校准可展示覆盖丢失/成本前沿，但用于质量选择的 material margin 仍待 Comparison Gate 在看候选输出前接受。

每个参数默认 **最多 3 个不同可行点**，没有实质差异可只保留 1 个并不做付费比较；一般比较最少需 2 个不同点，数量不足不是自动扩样理由。K×history、input×reserve 和 N×C 只有测量揭示交互才预登记不超过 4 个联合配置，不能三维乘积。每个 E 同一决策总 active configurations（含 baseline）上限为 tier 的 2 / 3 / 3，local 断点计算不等于创建这些 arms；交互需要 4 臂时必须分成可识别的有界配对或另经 Gate，不能借子实验绕过总上限。

| 参数 / 解锁决定 | 分布/observable 与取点细则 | 昂贵评测晋级与重评触发 |
| --- | --- | --- |
| recent N / D02 | M01 accepted 距离与链长的覆盖断点；N 只控制 A，跨窗必要组应由 B 补足；按 L/P/H 形成 N 范围 | union 必要组、I/O 均可行且实际解释输入不同才晋级；距离/噪声分布改变重评 |
| cross-history C / D02 | M02 每分支必要组最大排名及 union cutoff 阶梯；明确 C 是每分支还是合并 cap 并保留两种计数；M06 限制可行端点 | branch/union 未完整召回必须可见；语义下游可能改变选择才生成；分支/查询/语料分布改变重评 |
| final K / D03 | M03 不可分来源组数量，转换成 selector 实際 Turn/group 单位并记录映射；不能把一条纠正链硬截成 K 条 | 最少完整组点到有新增可选信息的 P/H；组合 history cap 仍留 required 才晋级；组数/组长变化重评 |
| history token cap / D03 | M04 真实 full-message 中最小必要历史及额外来源的增量，不使用平均每 Turn 长度 | 通过 mandatory/pack 与全局余量方可晋级；语言、framing、去重/来源长度变化重评 |
| state cap / D06 | M03/M04 必要投影长度为底线，非必要条目增量为阶梯；不可截 durable snapshot | 仅投影不同且有待决质量取舍才 E2E；纠正链/条目 schema/序列化变化重评 |
| input cap / D07 | M04 完整模板+query+mandatory+pack+可行 state/history，官方 context Hctx 与 output reserve 共同约束 | 输入 ≤ min(G, Hctx−O)，缺真实 accounting 不晋级；模型/context/pack/prompt 变化重评 |
| output reserve / D07 | M05 参考输出 tokens + 单一 baseline finish/usage，受官方输出上限和输入余量限制；旧 1024 仅 V0 对照 | 本地不能证明生成完整性，幸存点以 provider completeness/finish 检查；答案任务/模型变化重评 |
| interpretation cap / D09/D10 | 解释专用完整输入与有来源绑定/改写/控制 JSON 的参考输出，输入/输出分别计量 | 保留否定/来源且结构通过才语义 proxy；不与 generation token 余量混用；prompt/解释职责变更重评 |
| candidate I/O cap / D02 | M06 rows examined/returned、payload bytes、round trips、statement time，分别沿 required retention 取 L/P/H；记录扫描上界不可证明项 | 任一成本越界则 search_incomplete/失败，不为了 C 偷扫全库；数据量/query plan/hardware 改变重评 |
| retry/refetch cap / D12 | 基线额外发送/refetch **0**；确定性失败分类与可恢复 miss、PG 代价先验；UNKNOWN 无自动重发 | 当前候选集合只有 no-refetch 一个，例外不硬造第二点；触发后新 Gate 最多 2 个（无补取/单一有界策略），按完整来源所需最小补取次数推导，不猜整数；新失败类型或预算改变重评 |

解释/生成的 output reserve 均从实际官方容量扣除；pack、query、necessary 原文组不可按比例缩。可选项剔除仍超界时应不派发、不推进 accepted state，并记录 overflow；不是 Evidence 不足。参考 tokenizer、serializer 暂不可用时只报告 bytes/codepoints/proxy，不冻结伪真实 token cap。

## 6. 实验漏斗、样本与序贯晋级

| Level / stage | 门槛与最小证据 | 可淘汰 / 可得结论 |
| --- | --- | --- |
| L0 / CAL | 标签分布、来源/授权、真实序列化测量；上述 M01–M07 的可执行部分 | 不可行范围、同输入档、无可改变决定的实验；不宣称候选质量胜负 |
| L1 / DEV（实现后） | 隔离 PG、fake provider、确定 selector/assembler、scope、去重、overflow、幂等/fence/worker loss | 硬错误先停；mock 或标签计算不替代真实事务/重启/迁移检查；此处不得花生成费用证明确定性行为 |
| L2 / DEV | candidate/final coverage、intrusion、I/O、token、required retention；D09/D10 仅必要语义 proxy | proxy 可排除，不证明最终答案；paid proxy 占 DEV 同一物理调用池，不能额外加钱 |
| L3 / DEV | 只让幸存合规配置进入预冻结小 Dev 子集 | 不逐 arm 全套 Dev；固定前缀配对先隔离因素；留下一至两个有理由的配置 |
| L4 / HARD | winner 候选 + 一个仍可改变选择的 challenger；七硬例族；必要的闭环 rollout 独立会话 | old/noise/return/correction/ambiguity/negation/pressure；已支配 challenger 不为对称重跑；这里仍未冻结 winner |
| L5 / REG | 按 Evaluation S 冻结唯一 selected candidate 的 SHA/profile，另有固定 V0 兼容参照 | Regression 确认，不调参；失败保留、回 Development，新版本/新授权，不反复刷通过 |

序贯筛选最多三个预登记观察点：完成首个成对覆盖批次 → 完成其余 Dev 批次 → hard 批次。各批次在结果前固定 family IDs、arm、顺序/seed、repeats、质量 margin 与规则；不是逐 Turn 偷看挑停。原则上从最多 2/3/3 个 active configs 留至最多 2，再冻结 1；没有证据可区分时保持 INCONCLUSIVE，不硬凑 halving。幸存不保证得到完整预算。

每个有效 paired unit 共享 case/repeat/model/corpus/rubric 与控制输入；闭环每个 arm 用独立 Conversation，不能跨 arm 传 state。脚本化用户回复预写，所有真实生成前缀 Turns、澄清续轮也占 slots，不能仅计目标 Turn；因此下面的 target 容量在闭环时会降低。统一 receipt 可复用给多个 D，但不同 arm 实际输入不得伪装成配对。planned/attempted/evaluable/unavailable/失败全保留。

样本量不是旧 dev=32 的复制：先满足独立族和关键风险覆盖，再用 Calibration baseline 两次差异判断是否需要 repeats，选择族级 uncertainty 方案。稳定只是初步证据；默认每个比较 target 一次，只有预注册方差理由才从相同 stage 预算中给相同配对增加 repeat；repeat 消耗不能通过减少 critical 覆盖隐瞒。若当前方差证据不足决定 repeat，先完成追加有界 baseline 校准或标不足，不能看候选胜负临时增加。

Comparison Gate 指定 rubric 尺度、decision resolution/material-similarity margin、关键层要求和置信水平/区间方法。独立族足够才用 family-cluster 方法，预登记序贯观察适用的同时区间/误差分配；不在多次观察中重复使用普通终点区间声称显著。少族采用描述性配对与保守上下界，零次 critical 只是未观察到违规，不证明总体风险为零。预算不足以分辨 margin 就 INCONCLUSIVE。

## 7. Campaign 预算层级和准入

Campaign 下设 **CAL → DEV → HARD → REG** 的顺序门禁及独立 **RES** 储备。它们是同一 campaign 的分账，既不能把阶段顺序当作每阶段重新获全额预算，也不能自动转移余额。

执行链：**Campaign → Stage → Experiment ID → Arm → Conversation → Turn → Run → physical provider attempt**。同一 calibration/case 的重新运行、进程重启、显式 retry、Judge、解释、生成和失败发送仍引用原父账；新 Run 不清零 Turn/Conversation/Experiment。全局月预算是 campaign 外的额外父约束，跨月不能清零 campaign；其他项目调用占用全局余额但不伪装成本 campaign 的花费。

每层预算为独立向量：calls、input tokens、output tokens、worst-charge reservation、execution elapsed、local runtime、PG queries/rows/bytes/time、人审 units/minutes、工程 hours。任一维度不足即不准入。每次调用前按最大输出和已核验全输入预留各层预算；queued/inflight 也占额度。先登记 immutable attempt identity，原子保留/串行持久化；派发后即消耗 call，不论成功与否；确认未派发才释放调用额度。UNKNOWN 保持最坏 token/费用占用直到证据对账，不能填零或自动重发。初始串行方案最多允许一个 unresolved UNKNOWN；出现即暂停 campaign 新派发，保留其调用/token/费用并在 recovery 额度内对账。无法解决则终止本批并报告 INCONCLUSIVE，不能靠新 Run 继续花费。

现有 global lock 与 0.10 元保留不足以证明这套控制已实现。未来 paid 执行前必须证明共享预算准入与全局控制一致；可先用有持久 receipt 的串行小适配器，但不得用临时内存变量在重启后绕过额度。若落实需要新产品 schema/恢复机制，当前校准应延期并提交独立工程授权，不在本任务实现。所有 durable 产品 schema 变化仍须 Alembic。

### 7.1 公式与币种

用模型/phase 各自的 `I_p`、`O_p` 表示**未来校准/官方核验后签署的有限每次输入/输出 cap**；`I_* = max(I_p)`、`O_* = max(O_p)`。`G0` 是 CAL 固定 baseline 最大全输入 tokens，`O0=1024` 仅适用于当前 V0 generation pilot。未经核验的 cap 为 PENDING，不能以无穷大或代码字符上限代替。

对 phase p：`b_p = I_p × r_in,p + O_p × r_out,p + documented_other_max,p`，单位统一为元/token；官方按百万报价须先除 1,000,000。cached/uncached 分列；预留用合法最贵计费情形，不预期 cache hit/时段折扣。`b0` 为 CAL baseline 上界，`b_* = max(b_p)` 为后续单次调用保守上界。若其他费用不能给有限上界，paid 部分阻断。

- 估算：按实际可用 usage、rate-card revision 和 documented charges 分项相加。
- 实际：仅账单/官方实际 charge，附关联身份；取不到就是 unavailable，不改写估算为 actual。
- UNKNOWN：次数、未知 token/charge、保守保留值单列；和已知小计相加形成预算占用，不算免费。
- 签署的人民币 ceiling 必须 `M_t ≤ min(公式最坏总额, owner 所选现金上限, 当时全局剩余额度)`；若该值买不起全部 slots，减少未来可派发量，不能超支。全局余额必须在执行时私下核验，不能从源码 50 推断还有 50 元。

本次三档人民币估计均 **PENDING 官方价格/身份**，不是零元；下面给出的相异公式就是三档 total monetary ceiling 的提案，最终需 Human 签署有限金额。现有源码 50 元/月是额外硬界，不能自动提高；所有 token 公式必须代入可核验值并签署才能派发。调用 ceiling 不依赖价格，token ceiling 不依赖费率，现金不足时进一步缩小。

## 8. 三档容量：从覆盖和候选数推导

以下数字均是**owner-selectable 上限提案**，不是观测结果、置信保证或支付授权。三档共同保留全部硬不变量，差异是能够解决的 ordinary 取舍范围。一次 comparison target execution 的保守账本单位最多 **3 个 physical calls**：至多 combined interpretation + generation + 可选 Judge。跳过任一 phase 省下额度留在原账，不能自动增加目标或 arms。对单轮 V0 配对，自足 skip 省下解释 slot，可放一个 V0 generation；最多一个 Judge，baseline/争议人工审阅，不能漏计重建 baseline。若需第二 Judge/额外 phase，须先减少本批其它 slots 并重新预登记，超已批准语义则新 Gate。

### 8.1 provider 容量与总上界

| Stage / 推导 | Minimum / Lean | Recommended | Maximum / Ceiling |
| --- | ---: | ---: | ---: |
| CAL：固定 baseline targets × 2 | 4×2 = **8 calls** | 6×2 = **12** | 9×2 = **18** |
| DEV：最多 configs × targets/config × 3 | 2×12×3 = **72** | 3×16×3 = **144** | 3×24×3 = **216** |
| HARD：最多 2 configs × 七类的 targets/config × 3 | 2×7×3 = **42** | 2×14×3 = **84** | 2×21×3 = **126** |
| REG：唯一 candidate 的覆盖 targets × 3（含需要的 V0 重建） | 18×3 = **54** | 36×3 = **108** | 54×3 = **162** |
| RES：三用途的有限 calls 总池 | **18**（各用途≤6） | **24**（各用途≤8） | **36**（各用途≤12） |
| Campaign calls（全部派发，含失败/UNKNOWN/Judge） | **194** | **372** | **558** |
| Input tokens ceiling | `8G0 + 186I_*` | `12G0 + 360I_*` | `18G0 + 540I_*` |
| Output tokens ceiling | `8192 + 186O_*` | `12288 + 360O_*` | `18432 + 540O_*` |
| 人民币 ceiling 公式（另受 §7.1 双重余额限制） | `8b0 + 186b_*` | `12b0 + 360b_*` | `18b0 + 540b_*` |
| 预期可作决定 / 延期范围 | 最低风险覆盖与粗筛；一个必要对照，极少族仅描述性；延期 ordinary 微调/交互/额外重复 | 三个可辨别配置，较多独立族及七硬例层；仍无总体质量保证；延期低 VOI 与未触发策略 | 更细覆盖与预算内方差复核；最多三 active configs；不是统计效力承诺，不包含新架构/无限样本 |

DEV 的 12/16/24 targets/config 来自 6/8/12 个独立族容量×两个配对 views：Lean 围绕候选召回、K/history/dedup、state 剔除、解释激活、Rewrite、input/output 六个决策块；Recommended 增加两个测量支持的交互/边界族；Ceiling 允许六块各多一个独立来源族。只有可改变剩余决定的块才执行，块数不是独立性证明。HARD 的 7/14/21 来自七硬例层×每层 1/2/3 个 target 容量，优先不同族而非无理由重复。

DEV targets/config 是所有 E 共享的总容量，不是每个 E 再分配 12/16/24。不同 E 的 configured arms 总执行也必须在此池内。各 E 的 baseline、诊断 R/A/O、paid proxy、闭环前缀、repeats 均扣账；预算不够完成全部 E 就按可改变决定的 HIGH 顺序删掉非必要实验。REG 18 类的容量来自 Evaluation 类别覆盖（同一 target 可多标签），36/54 给每类更多独立材料容量；实际独立族数须由 manifest 确认，不能把重复 target 当新族。后续 release confirmation 不在此总额，单独 Human Gate。

各 stage input/output/现金最大值同样由本行 calls 推导：CAL 为 `c×G0 / c×1024 / c×b0`；其余为 `c×I_* / c×O_* / c×b_*`。精确 phase 清单可降低此上界但不可自动提高。RES 只是封存余额，未有用途签署前任何 arm 可用量为 0。

### 8.2 时间、local/PG、人审和工程分账

表中向量均为 Lean / Recommended / Ceiling；分钟与工时是资源治理提案，不是测得性能。人审一个 unit 是一个 target 标签核验、一个输出审核或一次争议/复审，重复审查另计；复杂 case 超 unit 预留时间时按实际分钟停止，不强迫 reviewer 赶工。

| Stage | setup / recovery 分钟上限 | 本地机器运行分钟上限 | review units 上限 | engineering hours 上限 |
| --- | --- | --- | --- | --- |
| CAL | 30/45/60；15/20/30 | 60/90/120 | 32/48/72 | 4/6/8 |
| DEV | 30/45/60；15/20/30 | 60/90/120 | 48/72/96 | 6/8/12 |
| HARD | 15/20/30；10/15/20 | 30/45/60 | 28/56/84 | 2/4/6 |
| REG | 15/20/30；10/15/20 | 30/45/60 | 36/72/108 | 2/4/6 |
| RES | 15/20/30；10/15/20 | 30/45/60 | 12/18/24 | 2/3/4 |
| 总计 | setup **105/150/210**；recovery **60/85/120** | **210/315/420** | **156/266/384** | **16/25/36** |

review 预估 ordinary 4 分钟、critical/争议 8 分钟，预算按全为 8 分钟保守预留，stage 人审 minutes cap=`8×units`。总人审上限 **1248/2128/3072 分钟（20.8/35.5/51.2 小时）**，包括标注、裁决、Bad Case、重复复核；实测耗时高于假设会先触发 minutes cap。这里明确人审可能比 provider 贵，owner 可选择更少范围，不能用自动 Judge 顶替未完成必要复核。

时间推导：串行启动；每个真实 provider attempt 采用 **≤45 秒的外层绝对取消界**（来自现有 Judge 45s 最大路径控制点，generation 仍从严服从原 35s/25s/Run deadline），同时为派发/记录预留至 **1 分钟/slot**。这不是模型 SLO；解释等新增 phase 需证明能施加外层期限才准入。单 comparison target 预留≤3分钟；未来产品 Turn deadline 仍由实际关键路径测量后单独冻结，不能把这里的 campaign slot 时长写入产品。

因此 stage wall execution ceiling = `setup + recovery + local runtime + calls×1分钟`，五阶段分别为 Lean **113/177/97/109/73**，Recommended **167/299/164/188/104**，Ceiling **228/426/236/272/146** 分钟；campaign 合计 **569/922/1308 分钟（9.5/15.4/21.8 小时）**。包括串行等待、backoff、失败/UNKNOWN 对账，未用额度不转 stage。进程重启不能重置已记录 elapsed；已达 parent deadline 则取消后续派发、fence 迟到结果并结算占用；外部服务可能继续计费，仍保留最坏预留。

按 owner 每工作日可给 4 小时人审/工程、一次最多 2 小时 machine session 粗估总 campaign 活跃交付周期：`ceil((engineering hours + review hours + wall hours)/4)`，即约 **12/19/28 工作日**，是保守容量规划而非承诺；Human Gate 排队另列 wait days。批准时填写 start/end 日期与 owner 可用时间，超 elapsed 或日历期限均停；不能无限暂停预算后继续用旧授权。

本地 replay 上界按数据和配置派生，避免“零 provider 所以无限测”：设该 stage 登记 target executions 为 `T_s`，local 配置上限 `A_s≤3`（CAL 仅一个 reference measurement），每项最多 **cold/warm 各一次**，`Q_s≤2T_s A_s B_s`，其中 `B_s` 是启动单冻结的查询分支数。每 query 的 row-examined/returned、byte 与 statement-time cap 为 §5 得到的有限 `R_s/L_s/D_s`；stage rows≤`Q_s R_s`、bytes≤`Q_s L_s`、PG time≤min(`Q_s D_s`, 本地 runtime cap)。任一值未定则只能静态计量，不能跑 PG。CAL 最多 16/24/36 target views，DEV/HARD/REG 使用 §8.1 的 executions，RES 按用途登记；禁止全库扫描绕过 returned-row cap。

本地 compute 记录 CPU/GPU seconds、peak memory、PG workload；无云机器租用额度，cloud monetary cap=0。电力等成本 unavailable 时明示，只报告 runtime，不能声称全部机器成本为零。原生已有服务可在另行授权的隔离实例使用，不启动/删除旧 RAGFlow。

### 8.3 实验与更低层的最大分配

在任何执行前签署 stage registry：对每个 E/measurement、每个 arm 指定 target/repeat 和完整预算向量，所有子账之和≤父账。同一 case 的 Conversation 总额是所有脚本前缀/目标/预写澄清分支和批准重试的和，取允许分支的最坏路径；Turn 预留所有 phases；Run 共享原 Turn 累计账。每个 attempt 上界为其 phase `I_p/O_p/b_p/timeout`，默认额外 retry=0。没有 Conversation/Turn 上界、expected head/receipt、每 E 最大 arms 或 exact phase 清单，就不派发。不能靠缩短单 Run 或新开 Experiment 名称规避旧决定的父账。

## 9. 人审与工程工作量治理

继承 Evaluation 更严格的人工要求：**所有 candidate critical 输出、critical guard failure、Development 硬例和全部失败、影响选择的 Judge 分歧、Regression 全部预定义 critical Turns/全部失败/分歧/零容忍案例均复核**，不是仅抽 representative failure。另为每个主要失败类建立代表 Bad Case 及首因；这可以复用既有复核 receipt，不重复花钱。关键标签必须在候选前 human-reviewed，普通 AI 草稿仍 provisional。

普通成功只做分层抽样：冻结 seed 后每 arm×primary_category 至少取一个可用成功项，并取该层其余成功的 10%（向上取整）；配对输出盲化 arm 身份并保持相同抽样范围。Judge 缺失/不可靠、普通抽样发现 material 错漏则冻结该层发布结论，预登记扩大复核或缩小结论，不临时把成功率当事实。10% 是可审阅工作量提案，不是可靠率保证；Comparison Gate 可在看候选前调整。

首次派发前同时预留其可能触发的 mandatory review units/minutes。剩余容量不能覆盖已知 critical/全失败最坏待审队列时停止新生成；优先完成在途 critical，不丢弃队列、不延迟登记到下一 stage。若 unexpected disagreement 导致额度不足，标 incomplete 并启动 RES gate 或结束；不能默默让 Judge 裁决。记录 unique cases、review events、Judge disagreement 数、owner critical adjudication 数、repeat reviews、估计/实际分钟。

工程预算覆盖数据整理、计量适配、可复用小 harness/config/replay/receipt、故障诊断和报告，不包含产品实现授权或“顺便”改架构。CAL 最多一个本地计量适配入口，DEV 复用一个参数化执行入口；每个 arm 启动前列出新增文件/代码职责、provider phases、failure modes、configuration、调试/维护/Trace 负担和工时估算。初始范围：无新基础设施、无 Conversation schema、无新 provider phase 类型（只有已接受 combined interpretation / generation / 可选既有 Judge），无自动恢复/repair 循环。

若任何 arm 需要新 schema、独立调度器、大量一次性 harness 或跨重启恢复语义才能测，先延期，附最便宜替代证据和新的 Human 工程授权请求；即使现金还有也不能继续。产品实现后可复用其真实 PG 测试接口，不把小型假实现包装成通过产品硬门禁。达到 hours cap 停止，完成现有 receipt/缺口报告；不能为完成实验无上限造基础设施。

## 10. 预声明停止规则

| 类别 | 判定方法（必须先登记） | 行动 |
| --- | --- | --- |
| Hard invariant | confirmed Memory→Evidence、Citation 身份破坏、cross-scope/conversation、stale accepted state、多有效结果、草稿 final、关键 entity/topic/Rewrite 漂移或其它 Feature I1–I8 违规 | 怀疑时暂停并 owner 定类；确认后立即停 arm 所有新增 paid 扩展。guard 已阻断与 accepted violation 分开，前者不是 accepted 污染，但该 critical 设计也须修复新 version 后另行评审，不继续烧 tokens 救同 arm |
| Dominance | 在预登记观察点，同成对人群与关键分层，另一可行 arm 质量至少不差且有实质优势，同时被比较 arm 在 calls/tokens/latency/费用/工程复杂度上无可改变选择的优势；无缺失关键 review，使用可用的同时区间或有限总体保守界 | 停止扩样；若只是均分低、CI 重叠/族太少、关键层反向或存在成本优势，不能宣布 dominated。质量在 accepted similarity 范围且更贵更复杂者按 S 淘汰 |
| Futility | 对冻结有限 planned paired population，以每项有界 rubric 差值的最有利未观察补全计算候选可能上界；关键层分别计算。若即使余下全有利也无法达到已签署最低门槛/beat incumbent 的 material boundary，且无成本/简单性胜出路径，则无决策价值 | 停该 arm；明确这是本有限计划决策界，不是总体显著性证明。若无法给界，只能预算到期 INCONCLUSIVE，不凭直觉说“不太可能” |
| Budget | 任意父层 cash/token/call/elapsed/local/PG/review/engineering 余额不足以预留下一单元，或已耗尽 | 不派发；不跨 stage、Run、月度或实验 ID 借额度；在途按保留额收敛，UNKNOWN 不释放；剩余不确定性明确报告 |
| Information / no-change | 已无任何可能结果能改变当前授权选择、输入完全相同或所问效果已有足够便宜证据 | 不运行/停止；给出决定及已用 receipt，不为 E 编号补齐实验 |

有限界示意仅定义算法：对 normalized paired score `d∈[-1,1]`，已观察总和 S，计划 M 项、剩余 r，则最有利均差为 `(S+r)/M`；不等族权重时用已冻结 family/category 权重逐项填充上界，不直接 Turn 微平均。缺失项保留最有利/最不利敏感性区间，不能删失败。只在全部允许的工程选择（含更便宜但相似）都无法胜出时适用；否则保持不可判。阈值/权重/观察点必须 Comparison Gate 先签，不沿用旧 -0.03。

Regression 首次固定协议终态即报告；critical 或质量 gate 失败不以追加成功样本抵消。修复形成新候选/协议并返回 Dev，原 Regression 已暴露，未来独立确认须新材料/授权。不存在自动跑到通过。

## 11. Contingency 与追加支出

RES 为 §8 单独封存的 calls/tokens/cash/time/review/engineering，不是其它 stage 的自动 overflow。最多三次用途：**一个意外 Bad Case family、一个确定性缺陷导致的协议纠正、一个本来 INCONCLUSIVE 的 focused measurement**；每类至多一次，默认调用上限分别 6/8/12（按 tier），总额仍18/24/36。纯本地纠正不需要 provider 时不能为用尽该类余额而生成。

每次先记录：原预算为何不足、D ID、可改变哪项决定、最便宜方案、触发证据、exact cases/arms/phase、各维预留及使用后的剩余量、受影响协议 revision。owner 书面批准释放后才动用；不得用候选已见结果重选阈值或把新 family 塞进旧 Regression。大架构变化与 E11/模型 repair 不因有 RES 自动获授权。

只有 HIGH 信息、关键不确定性阻塞且额外证据能改变决定、所有硬门禁可满足、人工/工程资源均承受时才值得申请更多。RES 耗尽或任何 accepted parent ceiling 扩张，必须新的 Human Gate；agent 不得调整上限，余额未用完也不能自行扩大协议。

## 12. 未来 Calibration 的精确交付契约

未来执行在项目内忽略目录 `.artifacts/v02-calibration/<campaign-id>/` 保存原始受控 receipts；不是本轮创建目录/文件。公开发布仅限 owner 核对的派生摘要/原创可分发材料显式 allowlist，不上传私人日志、凭据、provider 原始错误或旧 sealed 内容。hash 必须能定位获授权可读的原 bytes，不能只留不可恢复 hash。

| Artifact（逻辑文件名） | 必须内容 |
| --- | --- |
| `manifest.json` + `dataset.jsonl` | campaign/protocol/schema、确切 dataset identity/原文件 SHA256、语料/doc/version/license/hash、family/split/pair/critical 映射、作者/AI 标志、人审状态、采样/排除理由；原始数据不因报告重排重写 |
| `coverage.json` | Evaluation 十八类别、七 hard 层、语言/长度/距离/噪声/链长/pack 模式；独立族数、每层 target 数、缺口、未见/已暴露界限 |
| `local-measurements.jsonl` | M01–M07 身份；dependency-distance 原值/ECDF、branch/union 候选数及 required ranks、source-group 数、state/history bytes/codepoints、duplicate/supersession、search_incomplete、查询行/字节/时延/timeout |
| `accounting.jsonl` | exact serializer/input hashes、可解析 prompt/pack/state/history/framing 内容身份、component/full counts、生成 tokenizer/revision 或 unavailable、BGE proxy 分列、context/output 官方身份与上界论证 |
| `baseline-pilot.jsonl`（若未授权也交付 skip manifest） | 单一固定 baseline/tree/prompt/model/profile、case/repeat、input identity、attempt/dispatched/completed/UNKNOWN、usage/finish/latency/censoring、estimate/actual/unknown、receipt IDs、方差描述及局限；不包含候选胜负 |
| `candidate-ranges.json` | N/C/K、各 context/interpretation/I/O/retry cap 的 L/P/H 推导、原始 receipt 回链、相同输入折叠、可行性排除、≤3点/交互上限、未解缺口；提出范围而非推荐 winner |
| `budget-ledger.jsonl` + `budget-proposal.json` | 全层身份、每次预留/派发/结算/unknown、全局余额核验身份（不含 secrets）、calls/input/output/费用分项、setup/执行/恢复/local/PG、review units/minutes、engineering hours、每 stage/arm 余额、拟后续 caps |
| `review.jsonl` + `report.md` | critical 标签/输出、guard、Judge 分歧/owner 裁决、rubric 可用性、重复审查时间；测量结论/uncertainty、synthetic limits、不可测项、Comparison 缺项与 **NO WINNER SELECTION** |
| `receipts-index.json` | 上述原 bytes SHA256、工具/代码/tree/环境版本、采样/执行时间、原始 receipt identity 与访问位置、失败/skip；所有汇总可回算，hash mismatch 阻断引用 |

CAL 成功可以是“本地范围已知、paid/计量不足”，但须标 **PARTIAL / Comparison BLOCKED**；不能为了写 completed 虚构实测 tokens、baseline 方差或会话 PG 行为。合成数据只能验证有限构造，不能宣称自然会话质量或生产规模。

## 13. Comparison Protocol Freeze 的独立 Human Gate

以下全部齐备并引用接受 commit/owner/date，才可另行授权候选比较；缺一项不能以本 Plan/CI/PR merge 替代：

1. Calibration manifest/bytes hash、所需 M receipts、来源许可、人审/coverage、真实计量及足够 baseline variance；无法测量项有明确是否阻断理由，不能豁免硬边界。
2. 精确 dataset/splits/family/pairs/critical targets、schema/标签/rubric/指标分母；Development screening/hard 子集与 Regression 开启者/条件明确，未见 confirmation 保持关闭。
3. 精确 baseline code/tree/prompt hash/retrieval+conversation profile/model/revision/accounting/corpus/index/授权快照；新增尚不存在的 AB0 精确配置可由规范冻结，实际实现必须符合并在执行前提交一致性 receipts，不伪称已有实现。
4. N/C/K、history/state/input/output/interpretation caps、candidate I/O、product Turn/Run/Conversation 预算、retry/refetch、deadlines 的精确值与校准回链；范围变更视为新协议。
5. E1–E12 active/deferred 及触发条件、每实验最大 arms、配置单因素/交互、固定控制、全部诊断与 baseline 的成本、观察批次/顺序/seed/repeats 和必要 repeat 理由。
6. 样本量理由：独立族/关键风险、baseline 方差、配对效率、目标 decision resolution 与实际可承担成本；区间/置信水平/序贯方法或明确仅描述性方案。
7. hard gates、critical/overall/completion/noninferiority/material-similarity 与 S 选择规则，dominance/futility 计算及缺失处理；**签署前未使用候选结果选择阈值**，提供时间戳/访问记录。校准不得产生隐蔽候选排名。
8. finite call/token/现金公式已代值、官方 rate card/context/tokenizer 来源与访问日、global 月余额核验、UNKNOWN 最坏预留、每层 stage/E/arm/Conversation/Turn/Run/attempt 子账与预算执行证明；Judge、失败和重建 V0 已计入。
9. owner 接受人审 units/minutes、工作日容量、setup/elapsed/recovery/local/PG/工程工时、mandatory review 与抽样、争议裁决和 RES 释放规则。
10. 已签署候选实现范围及真实 L1 验证计划（实施/运行需另行授权）；进入任何付费候选评测前有真实服务幂等/fence/scope/identity/overflow 等通过证据，非现成 fake 的替代证明。
11. 唯一候选如何冻结进入 Regression、失败如何返回 Dev/新协议、后续 release confirmation/产品发布另行 Gate；无 winner 时保持 INCONCLUSIVE。

## 14. 待 Product Owner 决定与本次交付边界

Human Calibration Plan Review 需选择或修改：tier（Lean/Recommended/Ceiling）；各 stage calls/coverage/arms、人审和工程容量；是否另授权 baseline-only pilot（未选默认不调用）；是否接受 official pricing/tokenizer PENDING 的本地先行路线；有限人民币 ceiling/official identity 补齐流程；ordinary review 抽样与 mandatory 容量；日历窗口和可用工时；RES 逐次释放权。修改提案后须保留版本化记录，不能在观察候选结果后重写理由。

本次只提交本文和必要导航状态同步。Feature、ADR 与 Evaluation 已接受方法论不改。Git 显式发布 allowlist：`AGENTS.md`、`HANDOFF.md`、`docs/README.md`、本文；现有历史 source-candidate 打包脚本的旧 allowlist 不在本任务扩张，也不运行它生成 release 包。校准、provider、全量多轮数据、harness、schema/migration、N/C/K 选择、winner、vector Memory、Summary、Tool Runtime、tag/release/merge 均不发生。

交付完成于一条文档 commit 推送、Draft PR 和当次 Windows/Linux CI 到终态、工作树干净；停止供 Human Review，不等待/轮询人工决议，不把本 Plan 标记 ACCEPTED。
