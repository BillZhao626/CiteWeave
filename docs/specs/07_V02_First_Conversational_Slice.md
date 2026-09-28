# v0.2 First Conversational Slice — Feature Spec

Status: **ACCEPTED — Human Feature Review incorporated** · 2026-09-28

Implementation: **NOT_STARTED** · 不授权实现、模型实验或发布。

Human Feature Review：维护者于 **2026-09-28** 对提交 **`aa5755cbf70e552827f03211d2770a4dcff3626f`** 的本 Feature 原设计作出 **APPROVED** 决议，包含首版无自动 TTL/删除的保留政策；来源为本次明确授权的 Human Review 指令，公开接受记录见 [PR #3](https://github.com/BillZhao626/CiteWeave/pull/3)。接受行为设计不授权实现、校准、provider 评测或调参。

原设计采用有界 SDD + Feature / Evaluation co-design。基线经 fetch 核实：本地 main、origin/main、HEAD 均为 `0ccb4fc6cbaf6024a10096cf2a9df04bfdef2925`，起始工作树干净；[PR #2](https://github.com/BillZhao626/CiteWeave/pull/2) 已于 2026-09-28 合并。[架构](../V02_CONVERSATIONAL_RAG_ARCHITECTURE.md)状态为 **ACCEPTED — Human Review incorporated**，接受记录与实现状态不变。

本文只拥有首个切片的可观察行为；[Evaluation Spec](08_V02_Conversational_Evaluation.md)拥有数据、指标、实验与参数冻结记录。已有 Blueprint / Foundation / Governance 不改写；SQL 表、React 组件、精确路由名、最终 prompt 与数值预算均非本次定稿。文中的“必须”区分下列 A 类既有不变量与本次已接受的 Feature 行为；B 类经验选择仍为 UNSELECTED，设计接受不能替代执行冻结与实现授权。

## 1. 最小有用结果与范围

用户显式打开一个持久 Conversation，提出技术问题，经过插入无关轮次后仍能追问早先实体或返回旧话题；系统找回适用约束，无法消歧时澄清，技术回答仍有本轮授权 Evidence / PDF。刷新能继续，Trace 能解释历史如何影响了当前检索与上下文。

切片为：Conversation → durable Turn → A+B relevant history → topic/coreference/query interpretation → 原文或保真 Rewrite → 既有 documentary RAG → bounded Context Assembler → 验证 → accepted result + state 原子提交 → Trace / PDF。持久聊天记录本身不足以验收。

首版会话事实回答使用现有 `telecom-structural-v1` EvidencePack 路径；旧单轮默认 `m3-context` 及显式其他 profile 不改变。把所有旧 profile 适配为会话不是前提。会话 profile 独立于 retrieval profile，选择已有检索入口而不改其排序、prompt 文件或证据契约。本轮不产生新 prompt。

明确排除：Summary / compaction 实现、conversation vector index、跨会话长期记忆、个人画像、Tool / Function Calling Runtime、Agent 框架、OCR、多租户 RBAC、新数据库/服务、Celery 会话执行、自动跨重启续算、逐 token replay、会话分支/并行队列、编辑旧轮次、批量导入历史。另排除删除/擦除 UI、后台摘要和完整纠错管理台；最低限度的用户纠正通过新 Turn 表达，原始记录不覆盖。

## 2. 不变量与可调选择

| 类别 / ID | 契约 | 如何核验 / 决策归属 |
| --- | --- | --- |
| A / I1 | Memory 仅解释意图，历史回答、用户事实前提均不是 documentary Evidence；当前技术主张须有当前授权 Evidence | Evidence/语义支持分开检查；Evaluation 关键失败分类 |
| A / I2 | accepted Citation 物理解析 100%；accepted critical evidence / semantic-boundary violations 为 0 | Citation → Evidence → 不可变版本/span/PDF；无 Citation 不自动算通过 |
| A / I3 | Original Query、实际检索 query、输入 snapshot、所用历史、输出 snapshot 可检查且旧 Run 不重解释 | 身份/来源契约测试；ADR 0009 |
| A / I4 | 每会话一个活动执行；每 Turn 最多一个有效结果；失败、取消、stale、无效 Run 不推进 accepted state | PG 真实并发/重启测试；ADR 0006 |
| A / I5 | scope 与文本 query 分离，授权在接纳、读取和提交适用；不扩大到历史 KB 并集 | scope 变更、撤权和迟到提交测试 |
| A / I6 | 旧 v0.1 Ask、取消语义、reader、检索排名和冻结 Evidence offsets 兼容 | 固定 v0.1 单轮对照与契约回归 |
| A / I7 | A+B、Relevance first；recency 仅在已相关候选内辅助；全会话可定位，不能用近期窗口封死旧历史 | old-relevant / new-noise 配对；recent-only 仅作诊断对照 |
| A / I8 | 整体/阶段输入有界；不截断关键否定或破坏完整 pack；Summary 非首版前提，无无证据向量基础设施 | assembler 边界、overflow 与当前 pack 契约测试 |
| B / P1 | recent N、跨历史 pool C、最终 K、候选去重、词法/元数据检索、实体/任务/topic 规则优先序、recency tie-break | Evaluation E1–E5；不预设加权和 |
| B / P2 | history/state cap、output reserve、整体输入 cap、弹性 history/state 剔除顺序、overflow 提示策略 | Evaluation E6–E8；I8 限制可比较空间 |
| B / P3 | Rewrite 激活、确定性 skip 判据、合并/拆分解释、有限补取/修复 | Evaluation E9–E12；不能试验取消 I1–I8 |
| B / P4 | 每轮调用/重试/期限/费用、整会话资源预算、candidate I/O 上限 | 先测量与冻结预算表；无无限 retry，无 UNKNOWN 自动付费重发 |

## 3. 用户与 API 可观察契约（已接受）

使用显式会话 API 入口族，与 `/v1/queries` 分开；Pydantic/OpenAPI 定义，前端生成类型。下表是操作语义，不冻结路径拼写/DTO/HTTP 数字/SSE enum。

| 操作 / 场景 | 用户可见行为与后端责任 |
| --- | --- |
| 创建/重新打开 | 用户选择“新会话”，服务器产生 workspace 内身份和空 head；列表/链接可重新打开。UI 显示当前范围，不从另一会话继承记忆。创建操作重复按操作身份返回同一 Conversation |
| 提交 | 请求携带原文、显式有效 KB/文档范围、conversation profile、所见 head、幂等身份。原文/意图 durable pending 后返回可读 Turn/Run 身份；pending 不进入有效历史 |
| 响应丢失 | 客户端保留提交身份，可查回原 Turn/Run；刷新/网络重试用同身份，同 fingerprint 只观察，不能新建执行。同 key 异内容明确冲突 |
| 并发/旧 head | 第二独立提交明确 busy/head conflict，保留输入并刷新；用户再确认提交才新建 Turn。不自动排队或重定基 |
| 明确范围变化 | 每次提交传入 UI 展示的完整选择；首次由用户选择，后续可预填最近已提交范围但允许显式改变。无隐式全库并集、无在途默认 scope 编辑。新 scope 重新检查版本条件/状态适用性，变更不回写旧 Run |
| 澄清 | 展示待澄清问题及可辨别的候选实体/范围，不生成文档技术答案。澄清可 accepted，head 前进但实体仍 unresolved；用户回复为新的 Turn，关联控制结果。若用户换题则显式解除旧待澄清任务的活跃性 |
| 生成 | provisional delta 明确是草稿；断流未见 final 不能显示“已完成”。仅 durable accepted 后展示最终答案/引用；技术主张由本轮证据支持 |
| 证据不足/部分覆盖 | 无足够证据沿现有 profile 返回不足结果；部分支持只答已支持部分并指出来源缺口，不能编造平衡对比。控制结果可 accepted，只保存已明确意图，不把“没找到”写成文档事实 |
| 刷新/重连 | SSE 只观察，断线后执行可在有界期限内继续；读取 PG 终态/当前状态，不承诺重放漏失 token。后端重启经 reconciliation 显示 interrupted，不假装 provider 已续算 |
| 显式取消 | PG 仲裁 cancel 与 commit；cancel 先赢则 fence/释放自身槽、不推进 head；commit 先赢则显示已完成。provider 停止为 best effort，可能已计费 |
| 最小 retry | 仅无 accepted result、无其他活动执行、原 head/scope/profile 前提仍适用时显式创建同 Turn 的新 Run。retry 操作自身幂等；历史 Run 不覆盖。head 已前进要求新 Turn。UNKNOWN 提示费用可能发生，绝不自动重发 |
| Trace/旧引用 | 可查看本轮原文、改写、范围、输入来源、状态、证据、结果及失败原因；旧引用保留旧身份并检查当前查看权限。历史可读不意味着可用于新查询 |

首版保留政策（已随本次 Feature Review 接受）：本地 Conversation 原始提交、accepted 结果、失败执行记录、Run 使用过的 snapshot/context/profile 与引用依赖在首版无自动 TTL/擦除；UI 明示会保存在本地。关闭页面不删除。查询/Trace 有界不等于磁盘无限承诺；容量不足时明确拒绝新写入，不清除依赖来伪造成功。真正擦除、自动保留期或清理需另一个有撤回与引用依赖处理的 Feature Human Gate。现有文档 retirement 不破坏旧引用；原文件丢失/撤权时明确 unavailable/restricted，不能把不可解析结果继续声明为有效。首版不新增权限管理产品，但每个读取/提交仍应用既有 workspace/来源访问边界；不宣称已有完整动态 RBAC。

用户纠正是新 Turn：显式指明替换的实体/约束/旧回答，建立 supersession/invalidation 来源关系；只在该 Turn accepted 时发布新 state。旧文本和当时接受记录保留，未来选择排除已失效假设。无法定位纠正对象则澄清；不从 assistant prose 反向提取事实。内部发现的状态损坏禁用投影并从可验证原文重建新版本；无法恢复时明确失败。评测发现的历史关键违规仍是 blocker，不能用失效标记抹除。

## 4. Relevant History：先候选、后选择

固定输入 accepted head，只读取本会话授权的 accepted 历史及其来源；failed/pending/cancelled 不作记忆。历史用户陈述与 assistant 回答有来源类型，后者永远不作 Evidence。候选读取与最终上下文选择有各自快照、预算和指标。

1. **候选读取**：A 提供 recent accepted Turns 和有界 state；B 在 PG 的全历史可搜索范围按显式 Turn 引用、实体、任务、topic、有效约束、correction/supersession 关系检索。先过滤会话/授权/head，再进行有界候选合并；不要求 PG 扩展。N/C 是待测 cap，不是全库扫描许可；记录查询访问成本、分支数量与 `search_incomplete`。
2. **完整来源组**：候选带 Turn/Run、原文片段范围/哈希、关系及是否已被替代。纠正链与适用否定形成不可分的必要来源组；去重不丢不同 scope/version、冲突或 supersession 来源。跨窗口旧 topic 仍可定位，state 不是唯一查找入口。
3. **解释**：对自足且无未解决依赖/状态冲突的问题，确定性 skip 并记录理由；否则 topic shift、coreference、rewrite 可共享一次有界解释调用，分别给结果/来源。新题停用 topic-local 条目，显式会话约束仅在适用时保留；返回旧题重审后续修正及当前 scope，不回退 head。
4. **改写验证**：记录 Original、可选 Rewrite、实际 retrieval query；比对否定/实体/version/time/scope/条件及补全来源。检测关键漂移即阻断；仅原文可独立安全检索才 fallback 原文，否则澄清或明确失败。语义全等不能靠正则完全证明，仍需人工评测。
5. **最终选择**：在已建立相关性的候选中，按已冻结规则优先级和 K/token cap 选择来源组；保留验证指代的最低原文，排除被替代/无关历史。recency 只能作相关性层内 tie-break。记录每项入选/排除及候选中有而最终未选的必要信息，不能用一个总分掩盖两个阶段。

实验基线先不自动补取、不模型修复循环；这只是简单对照。有限候选补取只有在 E12 预注册、通过预算/效果验证后才能成为候选，UNKNOWN 永不因此重发。分离解释调用暂不进入首版产品候选；只有合并职责错误被定位后按 E11 gate 提案。

## 5. Context Assembler 契约

输入：Current/Original Query、显式用户 constraints、已验证解释与 state 版本、选中 Relevant History、完整 documentary EvidencePack、输出 reserve、冻结模型/tokenizer/预算 profile。Summary **absent**，不能用空摘要占位推导依赖。

输出：有来源类型的确定序列化输入 + 分项/整体计量 + 实际片段顺序和身份 + 丢弃原因 + `ready / clarification / overflow-failed` 决策。解释输入与生成输入分别冻结；不会把输入 state 与提交后的输出 state 混淆。

| 组件 | 类型 / 优先级 | 可改变与不可改变 |
| --- | --- | --- |
| 系统模板、消息 framing、原始问题 | mandatory | 计入整体输入，不静默截短原文；超限给明确失败 |
| 显式否定/entity/version/time/scope、验证指代必要原文组 | mandatory | 当前约束优先；完整保留来源与纠正关系，不把历史猜测覆盖原文 |
| 输出 reserve | mandatory capacity reservation | 从模型总容量扣除并设置输出限制，不作为输入文本；数值经 E7 |
| 本轮 EvidencePack | mandatory documentary contract | 对事实回答保留现有 profile 的完整 pack、标签、coverage/gaps；无证据进入不足控制路径。不得为了 memory 重新裁剪 pack/quote/offsets |
| 结构化 state | bounded | 必要条目升为 mandatory；可剔除不适用/可重复来源的非必要条目。持久 snapshot 本身不截断，记录本 Run 序列化投影 |
| Relevant History | elastic | K 与 token cap 都适用；按原始来源组剔除非必要片段，不能从否定中截半句；同内容来源关联仍留 Trace |

整体约束：`tokens(full_serialized_messages) <= min(generation_input_cap, model_context_limit - output_reserve)`；所有分隔符、元数据、标签、JSON escape、系统模板均计入，不能只加正文长度。解释阶段有独立输入/输出 cap；候选读取有行/字节/时间界限。仅有 BGE proxy 或字符上限不足以证明生成模型真实 token 上限，计量不可用时 fail closed，不虚称 ready。

拟比较的顺序仅限非必要部分：先剔除无关/失效内容（硬过滤），再比较“可选 history 先于冗余 state”与“冗余 state 先于可选 history”。Evidence 和 mandatory 不参与任意优先级排列。不采用固定百分比分配。

overflow：可选项按冻结规则去掉后仍装不下 mandatory + 完整 pack 时，不调用回答模型、不提交 accepted state，显示“当前问题和证据超出上下文限制，请缩小问题/范围或开启新会话”，保留原输入与失败 Trace。只有真实歧义且最小澄清 payload 也能装入其预算时才走澄清；不能把容量失败伪装为证据不足或让反复澄清规避 overflow。允许比较错误界面中“缩小范围”与“新会话”引导顺序，不允许自动删用户限制或缩 EvidencePack。改变证据预算需要新 retrieval profile 与另行回归审阅。

## 6. 原子接受、状态与 Trace

最终 commit 在同一 PG 事务验证当前授权、owner/fence、deadline、活动 Run、expected head、相关控制版本与尚无 accepted 结果，写结果/Citation/输出 snapshot、关联输入并推进 head/释放槽。无效 patch 优先缩到可验证的最小意图 patch；仍不合格则整轮失败。技术语义校验只能阻断已识别违规；不能把 physical validity 宣称为自动 entailment 证明。

Trace 至少包含：Conversation/Turn/Run/retry、输入 head/state、输入/输出 profile revision、Original/Rewrite/retrieval query、topic/实体/歧义来源、候选来源/计数/遗漏标志、实际选择与片段顺序、tokenizer/计量、各 cap/reserve、截断/overflow、授权范围/版本绑定、pack/Citation、验证/接受/取消/失效类别、阶段耗时、调用/usage/费用与 unknown。来源文本受同等授权；公共日志只含去敏身份和计数，不保存隐藏思维链或 provider 原始错误体。

历史查看、输入重建与重新执行区分；重执行新建 Run 并重查授权，不覆盖旧 Run。新 reader 与 `legacy-v1` / `structural-trace-v1` 共存。

## 7. 验收场景与实现前门禁

| 场景组 | 最低可观察预期 | 验证层 |
| --- | --- | --- |
| 追问/省略/旧限制 | 实体来源可定位；旧但适用约束在噪声后保留；当前技术结论仍有 Evidence | Evaluation 多轮分层 + UI→API→PDF |
| shift/return/correction | 不携带无关旧假设；返回不复活已替代约束；纠正只新建状态版本 | 数据集来源关系 + 真实持久化 |
| ambiguity/rewrite danger | 请求消歧、不得猜测；保留否定/范围；自足问题有 skip 路径 | E9/E10 + 人工语义审阅 |
| overflow/无证据 | 明确区分容量失败、真实歧义和证据不足；无草稿 final | 边界 fixtures + 长对话 |
| concurrent/retry/cancel | 同 key、双标签页、head 前进、取消/commit 竞态、迟到 cleanup 不产生第二有效结果 | 隔离 PG 集成，故障注入 |
| crash/reconnect | admission 后未启动、provider UNKNOWN、commit 前/后进程失效、final 丢失、PG outcome 不明均收敛 | 有界 reconciliation + 持久重启 |
| scope/source/legacy | 当前范围不借历史扩大，权限/源缺失明确；旧 Ask/Run/Citation/PDF 行为不变 | 现有检索固定对照、版本迁移与 reader 回归 |

本次已完成 Human Feature Review（含保留/范围/纠正/overflow UX）、Human Evaluation Methodology Review，以及四份 ADR 各自 Human Review：[0006 状态提交](../adr/0006-conversation-state-and-effective-commit.md)、[0007 信任边界](../adr/0007-memory-and-documentary-evidence.md)、[0008 上下文](../adr/0008-bounded-conversational-context.md)、[0009 profile/Trace](../adr/0009-conversation-profile-and-trace.md)。四个领域都直接约束此切片，不能推迟到业务代码之后。

同时须填完 Evaluation 的 pre-implementation budget/protocol freeze 表；尚缺测量时仅可在另行授权的校准任务中采样，不启动产品实现/调参。下一授权规划阶段为 **v0.2 Calibration Plan Freeze**；校准本身需单独有界授权，取得证据后再经独立 **Comparison Protocol Freeze Human Gate** 接受具体实验值。方法论接受不等于数值完整的执行协议已接受。未来实现使用 Alembic，验证 v0.1 PG/blobs 备份升级、旧 reader、新状态、重启及恢复；不承诺无损 downgrade。具体 schema/锁表达、React 组件、prompt/接口代码和基准 harness 延后。

Blueprint drift check：本切片服务持久技术追问；保留 PG/Qdrant/Redis/Celery/LocalBlobStore 职责、来源身份、scope、相关性优先和 opt-in 兼容；没有新基础设施或性能声明。Summary/向量/长期记忆/工具不被引入。以上 Feature 行为已获人类接受；本轮仅落实审阅记录，不开始下一阶段规划、校准或实现。
