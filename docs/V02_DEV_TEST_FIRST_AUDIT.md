# v0.2a DEV v2 — Test-first / bias audit

审计日期：2026-10-01。结论：**V02A_DEV_TEST_FIRST_REVISE_REQUIRED**。

只审查已有试卷与标签，不运行 DEV、不新增或修改案例、不修改生产或评测代码、不签 Human Gold。本任务未讨论或处理付费执行门禁。现有 v2 完整 SHA256 `3b1ef5dc37376cf26b5fb20aa8367d76ed2af5ccf376a312a62fc2d6dbcd20a7`；ID `citeweave-v02a-development-v2`，version 2。Human Review 仍 PENDING。

本审计由此前参与作者工作的同一助手完成，已知 arm 定义和 fake L1 观察；不能宣称独立盲审或消除作者偏差。下列第一阶段先记录与 arm 名称无关的需求，第二阶段才映射能力。审查使用当前原文、来源与既有契约；不以 fake 成功率为标签正确性的依据。第一阶段 D1.V2 的完整解释标签尚不具备冻结条件，第二阶段只作条件映射，不宣告需求已全部冻结。

## 1. 不依赖 arm 的试卷需求

表中“当前证据”均指本题授权版本的本轮 EvidencePack；历史/State 只说明用户意图。KEEP 仅为 AI 审计建议，不是 Human Gold 签字。隐藏 arm 名称后，12 题的核心能力均仍有意义；D1.V2 的话题关系标签仍需明确。

| View | 能力 | 具体失败模式 | 客观所需 / 明确不需要 | 通过条件 | 失败条件 | 与 arm 无关的存在理由 | Bias risk | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1.V1 | 唯一代词绑定 | 丢失它的实体，误取同文档另一设备 | 需 T1 的 Ferrule-Q 意图和当前冷却证据；无需 T2 原文或 Tray-R 周期 | Ferrule-Q，检查前冷却九分钟 | 四分钟、另一设备、无来源猜测或错误拒答 | 最小多轮指代能力；隐藏名称仍有效 | LOW | KEEP |
| D1.V2 | 跨干扰的旧意图恢复 | 最新实体替代原任务；话题标签漂移 | 需仍有效的 D1/Ferrule-Q 意图（历史或有效 State）和当前证据；无需旧原文作为事实或 Tray-R 周期 | 九分钟，排除 Tray-R；话题标签先需明确基准 | 四分钟、未获意图仍猜测、错误话题/状态评分 | 未结束任务被另一任务打断仍可恢复；核心题在隐藏名称后有效，完整标签尚不确定 | MEDIUM | REVISE |
| D2.V1 | 单轮兼容 | 自足题被强加历史依赖 | 需当前 Grove-Panel 报警证据；无需历史/State/改写 | 原问题检索，amber 指示灯 | Orchard/violet、虚构依赖或误澄清 | 空历史兼容是独立要求；隐藏名称仍有效 | LOW | KEEP |
| D2.V2 | 新话题与噪声隔离 | 上一设备/校准任务污染新问题 | 需当前 Grove-Panel 证据；无需 Orchard 历史或校准状态 | amber，原问题保持自足，不继承 Orchard | violet/校准答案、虚假依赖 | 与 D2.V1 配对检验无关前缀影响；隐藏名称仍有效 | LOW | KEEP |
| D3.V1 | 明示返回旧任务 | 展示话题覆盖旧设备/版本选择 | 需仍有效的 latch/release amber 意图（历史或有效 State）及当前证据；无需 display 原文或旧技术答案 | amber，three-notch，标 return，当前证据支持 | violet、display 信息、猜版本或错误拒答 | 返回已接受任务不应忘记当前选择；隐藏名称仍有效 | MEDIUM | KEEP |
| D3.V2 | 纠正与完整溯源 | 复活 amber，或只取纠正链一端 | 需 T1/T4 完整纠正关系、violet 当前意图和当前证据；无需 T2/T3、旧事实答案 | 有完整链时 five-notch，旧记录 superseded；缺链明确失败 | three-notch、复活旧项、缺链仍部分成功 | 纠正后的审计完整性是预先接受的不变量；隐藏名称仍有效 | MEDIUM | KEEP |
| D4.V1 | 识别真实歧义并澄清 | 默认/最新实体被当作唯一选择 | 需两个同等候选及尚未选择的意图；无需颜色证据来选设备 | 问清 North/South，不选候选，不生成技术答案，保留 unresolved | 默选一方或用文档颜色代替用户选择 | 无唯一指代时必须交还用户选择；隐藏名称仍有效 | LOW | KEEP |
| D4.V2 | 显式消歧与状态清理 | 继续澄清、选 North、遗留 unresolved | 回答需当前明确 South 和当前 green 证据；清状态需 pending 状态身份，无需 T2 原文作为回答来源 | South/green，解除适用 unresolved；原文覆盖 N/A | blue/再次索要已给选择、pending 未清、人工原文分母 | 明确补充应使交互继续；隐藏名称仍有效 | LOW | KEEP |
| D5.V1 | 省略实体与时间/情态保真 | 把“必须做”误读为允许做；忽略禁止时段 | 需 T1 Quill m4、问题的 24 hours、当前初始化计时规则；无需无关历史或猜设备版本 | No；初始化后不足 24 小时不得 relay | 强制/允许提前 relay、改变设备/时间或漏禁令 | 判断义务必须依据规范，不能只迎合问法；隐藏名称仍有效 | LOW | KEEP |
| D5.V2 | 显式否定的改写保真 | 删除 NOT、翻转 Yes/No、改变时间 | 需 Quill m4 意图、NOT/24 hours 和当前证据；无需新的版本/条件假设 | Yes，保留 NOT，初始化后不足 24 小时禁止 relay | 丢否定、提前 relay、时间漂移 | 单词否定改变问题极性，是独立安全风险；隐藏名称仍有效 | LOW | KEEP |
| D6.V1 | 当前文档依据与自足检索 | 用维护记录回答应急措施 | 需当前范围内 contingency 的 gravity bypass 证据；无需维护历史或 ledger 原文支撑应急结论 | brownout 时 gravity bypass，引用当前 contingency | 维护周期作答案、无支持技术主张或误拒绝 | 同设备不同文档用途必须区分；隐藏名称仍有效 | LOW | KEEP |
| D6.V2 | 缩小范围后的证据不足 | 偷用范围外 contingency、把缺证当容量错误 | 需当前 ledger-only 范围和其不含应急措施的材料；无需旧宽范围/State/外部知识 | 明确证据不足，不给 gravity bypass 技术结论 | 扩 scope、引用被排除文档、历史升格 Evidence | 当前授权范围控制答案权威；隐藏名称仍有效 | LOW | KEEP |

### 必须先修订或澄清：D1.V2

T1 选择 D1-task/Ferrule-Q，T2 使 D1 请求 pending；T3 原文为 “Now check Thermal Tray-R's standby display.”，其元数据 topic/task 均为 `tray-display`。目标原文重新指向 “the D1-task inspection”，query signals 又为 D1-task；但 `topic_relation` 是 `continue`，解释参考也沿用该值。

若以最近对话焦点判定，这是回到 D1；若以仍 pending 的 D1 子任务内部判定，也可称继续。现有标签没有给出选择该基准的独立规则。active Ferrule-Q 意图是否仍有效与对话当前是否返回旧任务是两个问题；Owner 接受前者，不自动决定后者。不能把保留该 State 项、默认 author 参数或 fake guards 通过当作 `continue` 的语义证明。

需由 Owner 明确 topic 判定基准，并对齐 D1.V2 的关系、参考解释、话题/状态评分与必要标签；也可明确 T3 是不改变主任务焦点的旁支，但不得为保留某 arm 结果而改题。D1.V1 与 D3.V1 的相应定义须检查一致性；目前不要求改它们。Ferrule-Q、九分钟、当前 Evidence 权威及无原文/B 信用的 State 边界均不因此推翻。**本任务不提出替换数据字节、不生成新版本。**

这是解释标签欠确定性，不是证明数据为了某 arm 获胜。其重要性在于已接受评测要求单列 topic/状态正确性；技术答案正确不能掩盖该维度不能一致判分。依据见 [Architecture §5.1](V02_CONVERSATIONAL_RAG_ARCHITECTURE.md#51-topic-shiftcoreference-与-rewrite-的不同责任)、[Feature §4](specs/07_V02_First_Conversational_Slice.md)、[Evaluation §3–4](specs/08_V02_Conversational_Evaluation.md)。

## 2. 需求之后的能力映射

| 能力/题 | EXISTING_V01_CONTRACT | cp-r-v1 | cp-a-v1 | cp-ab0-v1 |
| --- | --- | --- | --- | --- |
| 自足、当前文档、范围/不足：D2、D4.V2 回答部分、D6 | 有单轮问题与当前文档范围，理论可满足文档回答部分 | 可满足，无需历史补全 | 可满足，无需因有 State 就强行用它 | 可满足，无需 B 恢复 |
| 近期继承/歧义：D1.V1、D4.V1、D5 | 缺少 accepted 对话意图，不能凭无历史的技术答案宣称恢复指代；具体模型结果未知 | 近期原文可提供意图 | 相同近期原文加有效 State | 相同能力；这些题不要求额外优势 |
| 普通旧语义意图：D1.V2、D3.V1 | 不提供前缀意图 | 近期材料未含唯一旧实体，不能安全补全 | 给定有效 State 能提供当前意图；零旧原文/B 覆盖 | 旧原文可由 B 恢复，另计来源覆盖；不预设答案更好 |
| 原子纠正：D3.V2 | 无完整对话纠正来源组 | T4 可见但 T1 不可见，完整性要求不满足 | State 可知 violet，但不能替代原子来源组 | B 可以恢复完整组；下游技术/纠正正确性仍待实际评审 |
| pending 清理：D4.V2 | 无该对话状态管理能力 | 无 State，不要求清理不存在的条目 | 应清除本 arm 已有 pending 条目 | 同左；不是 B 原文恢复题 |

D1.V2/D3.V1 客观需要的是**当前有效的用户语义意图**，并非指定必须通过某个 State 数据结构：完整来源或经接受的有效 State 都可提供；使用哪条路径是能力映射的结果。State 不提供冷却/对齐技术事实。D3.V2 的 T4 文本足以命名 violet，但不足以满足独立的完整纠正溯源契约；不能混淆“猜得出技术答案”和“来源链完整”。完整性依据是 [Comparison §4 D03](V02_COMPARISON_PROTOCOL.md)、Feature §4，早于 v2 标签和模型结果。D4.V2 已明确 South，旧 T2 对回答没有必要原文依赖；对状态清理的上下文需求另计，不能造来源覆盖分母。

普通旧意图题因语义状态保留而区分能力具有独立理由；原子链题因不变量而区分能力也具有独立理由。但 D1.V2 标签未清楚前，不冻结其完整期望，也不把 State-only 评测产物等同于生产 Acceptance。V0 的当前资料可能让模型猜中实体；偶然正确不能替代有来源的意图解析。本审计不预测真实胜率或选择赢家。

## 3. 泄漏与适应性过拟合

- v1/v2 本地报告均为 `DEV_NOT_RUN`，各含 37 个 `FAKE_L1_NOT_DEV` receipt；外部调用及 Judge 为 0，call 类型为 fake 或 serializer-only。此次只读验证，没有运行这些 fixtures。现有任务记录、作者流程和本会话与“v2 标签作者前不存在真实 DEV 输出”一致；这不是对外部账户/所有未登记运行的全局取证证明。
- 先前别的实施任务有一条单独 real smoke；不能说项目从未有过任何模型输出。该 smoke 不属于这 12 题，未用其输出定标签。也不能把 fake fixture 返回当模型测量。
- v1→v2 原因来自 Owner 的 REVISE：普通有效语义状态被错误地绑到旧原文要求；State 增量不可识别；D4.V2 人为来源分母。D3.V2 原子链未放松。没有真实 DEV 低分推动修订。修订确实考虑了已知 arm 的可辨识性，因此不宣称作者从未考虑比较结果；本表重新检查其独立能力理由。
- v1 原始 SHA256 `f33f96f51f1e5bf310bc9034e673c40ffd74f6a1fe91a4a62d2a1af45be0dd44` 经字节复核，与 [v1 proposal](../evals/citeweave-v02a-development-v1.json)、[保留的人审表](V02_DEV_DATA_REVIEW_V1.md)及 REVISE 记录一致。v2 有独立 ID/version/完整 hash，各 view/source/protocol hash 校验通过；七份来源/版本与 v1 相同。
- 作者代码只生成原创源文和 Development 数据；loader 只允许当前 Development，拒绝 REG/Holdout/未知身份，既有测试覆盖读文件前拒绝。记录为 sealed 内容 absent/inaccessible；本次未访问任何 sealed 文件。资料和实现记录未发现使用 REG/Holdout 的证据；不能从一个布尔字段宣称全局泄漏不可能。
- 若未来 v2 被批准为 Human Gold：v2 数据/标签/hash 与真实结果永久并列保存；不能依 DEV 结果修改同一 identity/version。发现缺陷必须保留 v2/结果、登记理由并创建新的 dataset version/hash，重新人审。此次发现标签问题也不重写 v2。

## 4. 集合覆盖与缺口

| 维度 | 已有试题及覆盖范围 |
| --- | --- |
| pronoun / omitted entity | D1、D5；唯一已接受选择，非自然分布多候选测试 |
| old-but-relevant / recent noise | D1.V2、D3；刚跨 recent-2 的短前缀，不代表长程记忆总体 |
| topic shift | D2.V2、D6；覆盖新任务回答不受旧资料污染，前缀没有实质旧 State 需停用，状态退休能力的覆盖有限 |
| topic return | D3.V1/V2；D1.V2 关系欠确定，不能先算标签正确 |
| correction / supersession | D3.V2 一次实体/release 替换；未覆盖长链、冲突纠正或重新激活多约束 |
| ambiguity / clarification | D4 二选一及明示补充；未覆盖无候选、指令冲突、多轮澄清失败 |
| rewrite-required | D1、D3、D5 的实体/版本补全；证明有来源补全需求，不证明真实检索收益 |
| negation / protected constraints | D5 成对极性，NOT/24 hours；m4 随实体保留，未独立改变版本/计时条件 |
| document-scope / evidence-insufficient | D6 配对，问题不变而排除支持文档；未覆盖部分可答或版本撤销 |
| single-turn compatibility | D2.V1，自足噪声 D2.V2，D6 空依赖；实际 V0 非劣效未运行 |
| 长上下文及边界 | 12 题不覆盖人口长会话；既有单独 L1 容量/原子组/权限/幂等故障验证不能折算作新的语义样本 |

六个预先要求的 family 各有配对目的：[Comparison §2](V02_COMPARISON_PROTOCOL.md)。D1 与 D3 同含旧实体，但一个是代词干扰，一个是明示返回与纠正，不能当独立重复样本；同 family/view/source 相关性必须保留。D2 增加噪声、D4 增加明确选择、D5 只改 NOT、D6 只缩 scope 都是可解释的对照，不为各 arm 分数平衡。数据集中同文档直接陈述、人工任务 ID、人工 signals、简短英语和理想有效 State 会使定位/答案很容易；Bias risk MEDIUM 的旧意图/纠正题尤其不能外推真实语义检索能力。不新增凑平衡案例，不声称统计总体覆盖。

## 5. 逐题参考标签核验

逐一阅读十道文档答案的原始源句及问题，不仅运行 span 精确性检查。D1 两题：用户意图决定 Ferrule-Q，材料明确检查前九分钟，Tray-R 四分钟不适用。D2 两题：Grove-Panel 的 amber 与 Orchard 的 violet 属不同设备/任务。D3.V1：未纠正的 accepted release 为 amber，对应 three-notch；D3.V2：T4 明确改为 violet，对应 five-notch，旧 amber 只保留溯源。D4.V2：原问题明确 South，材料明确 green，North 的 blue 不适用。D5 两题：材料禁止初始化后不足 24 小时 relay；V1 对“must relay”答 No 并说明禁止，V2 对“must NOT relay”答 Yes 并重述禁止，时间与 NOT 标注正确，不把“不必须”当“允许”。D6.V1：授权 contingency 明确 brownout 时 gravity bypass。

D4.V1 的两个同等候选无唯一用户选择，澄清参考针对缺失选择，不能让文档代替选择；不要求技术 support span，required aspects 为空不代表忽略控制行为。D6.V2 当前范围只有 ledger，文本明确没有 brownout 措施；虽另一个文件存在答案，也必须证据不足，空技术 aspects/support 适当。所有十道技术参考的 required aspects 与上述主张吻合；引用标签须按实际当前 pack 解析。引用精确不是语义支持的充分条件，源句、设备、条件、版本、范围一起核验才支持本审计判断。

T1 为 D1/D3.V1/D5 的意图来源和 raw-coverage denominator；在 State 允许替代语义恢复时，它仍是原文覆盖的对象而不是唯一语义成功路径。D3.V2 组是 T1/T4 原子链，D4.V1 的 T1 支持候选集合。D2/D4.V2/D6 没有必要原文组，N/A 合理。D1.T2 是保留 pending 的背景控制，不含待补实体；列为 final-history 非必要项不应被解释成“对会话完全无语义”。D3 的 display 记录不提供 latch 意图；D6 的宽 scope 历史尤其不能作为窄 scope Evidence。D4.V2 没有 irrelevant-history 项不等于 T1/T2 都应放进事实回答，它们的状态/分支角色与所需原文分别报告。

解释中实体/版本补全都有 accepted 原始来源或经 Owner 接受的有效 State；当前事实不从 State 提取。D1.V2 的 topic 标签欠确定是唯一此时要求 REVISE 的实质问题。其他题在本文声明的有限前提下 KEEP；上述覆盖缺口及人工 signals 的理想化限制不应伪装成已验证能力。

## 6. 停止与完整性

本次只读校验通过：v1/v2 完整 hash、全部 per-view/source/protocol hash、七份原创 PDF/canonical 源 hash、十个支持 span 的范围、既有两版报告全为 fake/no DEV。没有重新生成 proposal、review surface 或 fake 输出，没有新增测试、启服务、读 sealed 内容或调用模型。原有代码/数据/测试/两版审阅文件的字节保持不变。仅增加此审计记录及 HANDOFF 导航。

数据集级结论：暂不能冻结全部 Human Gold。**精确受影响 view：D1.V2，`topic_relation` 与对应参考解释/评分基准**。先独立明确当前话题与 pending 子任务的关系，维持已接受 State/原文/Evidence 边界，再另行授权修订新版本。其他题不因某 arm 的预期表现而改。停止在本审计，不签 Gold、不运行 DEV、不处理付费门禁。
