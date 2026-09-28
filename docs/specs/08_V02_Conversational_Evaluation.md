# v0.2 Conversational RAG — Initial Evaluation Spec

Status: **PROPOSED — awaiting Human Evaluation Review** · 2026-09-28

Protocol: **DESIGNED, NOT EXECUTABLE UNTIL FREEZE** · 未执行 provider 评测，未选择获胜策略。

范围为[首个 Feature 切片](07_V02_First_Conversational_Slice.md)。本页拥有参数、数据、量表、比较与选择协议，不定义产品 SQL/API。遵守[已接受架构](../V02_CONVERSATIONAL_RAG_ARCHITECTURE.md)和[Governance](../ENGINEERING_GOVERNANCE.md)；硬不变量继承 Feature I1–I8，新的实验方法为提案。既有分数、历史 holdout 和本页草案都不构成 v0.2 质量证据。

## 1. 决策顺序与冻结门禁

每个经验选择遵循：问题 → baseline → 合理备选 → 预先定义评测维度 → 控制比较/消融 → Bad Cases → 质量/延迟/成本/复杂度权衡 → 决策记录 → 重评触发。本轮冻结的是供审阅的维度/协议草案，**不虚构最终概率性发布阈值，不把候选结果用来倒推门槛**。

采用两次签署点，解除“没有多轮数据却要先选 token 值”的循环：

1. **Calibration plan freeze**：在采集前批准校准材料来源、独立 calibration split、采样维度、计量器和候选范围推导法；允许另一个有界、明确授权的离线测量任务。若需 provider usage/延迟，另行授权费用与调用范围，不能由本任务或文档接受自动推导。
2. **Comparison protocol freeze**：只依据校准分布、产品风险/可承担成本和固定基线的方差证据，填入下表并由 Human Evaluation Review 接受；在产品实现和任何用于选参的候选比较前完成。若方差需要 baseline-only pilot，必须预注册、仅在 calibration 运行，不能看候选胜负来选容忍度。随后实现符合已接受 Feature 的候选，按分阶段协议比较。

| 冻结记录必须填写（本轮均非数值已定） | 依据 / 接受条件 |
| --- | --- |
| 数据/schema/原文字节哈希、族/split 映射、每层数量、关键轮次、标注状态、样本量理由 | 覆盖下列类别及资源边界；方差/目标区间精度与费用共同论证，不复制旧样本数 |
| rubric/脚本版本、严重度、分母、争议裁决、配对人群、interval 方法/置信水平 | 本页第 4–5 节 + 校准可行性；有足够族再解释统计区间 |
| baseline 精确代码/tree、模型/provider revision、prompt 字节、retrieval/conversation profile、语料/index/tokenizer | 无缺失身份；不以新模型运行旧代码假称历史原成绩 |
| N/C/K、history/state/input/output cap、解释 cap、候选 I/O cap | 第 2 节测量推导；每个值必须能链接依据 |
| 每 Turn/Run 与整 Conversation 的调用数、总 token、费用和 wall-clock 上限；retry/refetch 次数；期限/资源耗尽行为 | Feature 的失败/显式 retry 契约；成本 unavailable/UNKNOWN 不能算 0，不能用新 Run 规避会话总额 |
| E1–E12 实際候选清单、变化因素、固定量、交互、运行次序/seed/重复次数/预算 | 只保留少量可辨别备选；重复次数由 baseline 方差与预算确定，不挑最好一次 |
| 总体/关键分层质量、完成率、非劣效容忍度、material similarity 定义与选择规则 | 产品错误代价 + rubric 尺度 + baseline calibration；在候选结果可见前书面接受 |
| Regression/后续 confirmation 开启条件、操作者/保管者、候选 freeze SHA/profile、失败后处置 | 不用 Regression 调参；后续发布标准单独获接受 |

历史 `-0.03` 配对容忍度在本协议中**不继承，待替换**：不同多轮人群、缺失分母与 rubric 不支持直接迁移。这里的决定是禁用该数值，新的 margin 需按上表接受后才能作比较结论。任何未填项阻断实验选型与实现授权；不会因为本文可审阅或 CI 成功而隐式补值。

## 2. 当前仓库证据与参数校准

审计基线为 `0ccb4fc6cbaf6024a10096cf2a9df04bfdef2925`；只定向读取当前代码、公开 fixture 与数据结构，没有读取私人审计、运行凭据、历史实验报告或 holdout 题文，没有访问本地运行数据库/付费 provider。

| 已核实证据 | 可以推出 | 不能推出 |
| --- | --- | --- |
| [profiles.py](../../src/citeweave/profiles.py)：structural seed ≤1024 BGE proxy tokens/3200 字符/64 spans；pack ≤2048 proxy tokens/6400 字符/96 spans；seed 数 single=4、compare=6 | 旧 EvidencePack 比较条件原样固定，profile 不是会话预算 | generation tokenizer token 数、history/state/output 的分配比例 |
| [evidence_selection.py](../../src/citeweave/evidence_selection.py)、[context_tokens.py](../../src/citeweave/context_tokens.py)、[query_evidence.py](../../src/citeweave/query_evidence.py) | `prompt_json` 实际序列化 pack 由 pinned BGE tokenizer 计量；本轮不得破坏 pack | BGE count 等于 DeepSeek 输入 count |
| [answering.py](../../src/citeweave/answering.py)：structural messages content 总长度 ≤12000 codepoints；生成阶段 timeout ≤35s | 旧路径字符/阶段保护要保留为对照 | 12000 是模型 context window、35s 是 v0.2 多阶段 SLO |
| [llm.py](../../src/citeweave/llm.py)：请求 `max_tokens=1024`；[settings.py](../../src/citeweave/settings.py) 默认 `deepseek-flash`、query deadline 60s、全局月预算 50 元 | 1024 可作为不变的旧单轮 output 对照点；全局已有预算约束 | 当前 provider 官方模型上限、每会话预算或 v0.2 输出最优值；代码默认值不是现场配置 |
| 当前 prompt UTF-8 解码后 codepoints：answer-v1=248、answer-telecom-v1=775、answer-telecom-consistency-v1=1527 | 固定模板本身有成本；比较必须冻结所选模板与哈希 | 不包含动态 query/pack/framing，不能据此算可用历史 tokens |
| [公开 telecom 数据](../../evals/citeweave-public-telecom-eval-v1.json)：实际 dev=32、regression=24、safety=16；holdout content absent / NOT_YET_SEALED；只测可见 dev question，长度 47–209 codepoints | 现成单轮结构/来源元数据可借鉴；不是多轮样本；总文件 SHA256=`d133f682dd0724c7479aeb0948e846dd148653061b9e3b9fefaf5eda966582a7` | 历史距离、会话噪声、source-group 长度、真实 token 或 latency 分布；旧 split 不是新的未见集 |
| [原创结构 fixture](../../tests/fixtures/telecom_structure/README.md)、[答案一致性 fixture](../../tests/fixtures/answer_consistency/README.md) | 可用原创 PDF/span 做确定性边界测试；一致性 fixture 仅有限人工注释对照 | synthetic tokenizer 或注释验证证明自然文本语义 enforcement/真实模型质量 |
| [既有 evaluation](../../src/citeweave/evaluation/comparison.py)、[metrics](../../src/citeweave/evaluation/metrics.py) | 已有配对 win/tie/loss/unavailable、数据/rubric 身份比较、独立物理引用检查可复用概念 | 已有多轮 harness、history 标注、conversation-level cluster 推断或本轮评测完成 |

以上数值只支持旧路径固定控制点；**本轮没有任何新 N/C/K/token cap 的经验最优值或可靠候选数值网格**。也未取得足以证明多轮范围的公开 runtime trace 分布。模型总容量与价格不能仅凭源码推断，未来校准需锁定当时官方模型规格/计费版本和实际 usage；本轮不为规划去调用模型。

校准集合独立于用于胜负比较的 Development，至少跨：历史距离、同 topic 实体数、插入噪声数量、纠正链长、topic return、语言/符号长度、single/compare 文档覆盖、query/pack/输出长短。用原创技术小文档与有许可材料，不用旧 sealed 内容造题；按第 3 节 provenance 标注。预先确定采样层数/每层数量及覆盖理由，不能边看候选表现边加有利案例。

| 参数 | 必需测量 | 范围推导与冻结方式 |
| --- | --- | --- |
| recent N | 必要来源距当前的 accepted Turn 距离、依赖链长度 | 按标注依赖距离的覆盖转折点及资源边界生成少量互异窗口；recent-only 包含跨窗必漏案例；不是以最优答案结果选窗口 |
| cross-history C | 每分支合格候选数、必要组出现位置、去重前后量、PG 查询行/字节/耗时 | 选能区分截断遗漏与访问成本的覆盖拐点；超预算值淘汰。小 cap 的遗漏必须报告而非隐藏 |
| final K / history cap | 完成问题所需最小来源组的数量、真实序列化 tokens、噪声密度 | 从最小完整组到额外上下文的覆盖拐点取少量可行档；K 与 token cap 小型交互比较，不将相同实际输入算独立候选 |
| state cap | 必要与非必要结构条目数、序列化长度、supersession 来源成本 | mandatory 必须保留；比较能覆盖不同非必要量的边界，不能压缩到丢必要否定 |
| output reserve | 人工参考答案/澄清的目标 tokenizer 长度，另授权 baseline-only usage 的截断/finish reason | 1024 仅保留旧对照；根据输出分布与模型上限提出邻近可行点，不能预设加倍策略 |
| input cap / interpretation cap | 完整 framing+模板+query+mandatory+pack，生成 tokenizer 总数；模型 context 上限与输出 reserve | 由真实可行余量与延迟/费用限制取边界点，分别校准解释和生成；BGE proxy 不能直接相减 |
| 调用/时间/费用/会话总额与 retry/refetch | baseline 调用路径、失败类别、运行时方差、UNKNOWN、会话长度/累计 usage；本地 PG 时间分布 | 先批准测量花费，再冻结产品/实验上限。未测实际 charge 只报告版本化估算，不替代账单 |

记录原始去敏测量与字节哈希、计量器版本、采样/排除理由、候选推导函数或明确规则、最终档位和批准 commit。计量器不支持所选模型时，先解决可验证的计量或保守有依据的上界，不能凭字符倍数猜测。校准不选择 winner；范围冻结后任何扩展视为新协议版本，在新比较结果出现前接受。

## 3. 数据集结构、类别与 split

设计新的 multi-turn schema，不在本轮生成完整数据。文件名/schema 版本将随 dataset freeze 确定；以下是记录契约，不是运行时 Pydantic schema。

| 层 | 必填信息 |
| --- | --- |
| dataset manifest | dataset/schema revision、原文字节 SHA256、作者/日期、AI-assisted 标识、license/redistribution、语料/文档版本哈希、split seed/分组映射、每层数量、标注/review 状态、protocol revision |
| scenario | scenario_id、family_id、实体/任务/template/来源族、split、类别多标签与一个 primary_category、pair_group、principal/workspace/scope、初始 accepted 历史、脚本化用户 Turns、干扰变量、可用文档/固定版本 |
| target Turn | turn_id、原文、显式范围/限制、前驱/待澄清关系、期望行为类别、允许的解释/改写等价类、entity/version/time/negation/scope assertions、topic transition、允许/必须失效的 state 条目 |
| history labels | required dependency groups（组内等价来源可任选，组间均需）、optional-useful、irrelevant/forbidden、supersession 图、必要原文 span/来源类型、适用 head、required vs redundant state、不可拆来源组 |
| evidence labels | answerability、required aspects、允许 Evidence support groups、不可变 doc/version/canonical hash/span/PDF locator、当前 scope 下支持/不支持的技术主张；新发现合法替代证据按盲态裁决，不能只认有限 gold overlap |
| expected outcome | answer/clarification/evidence-insufficient/overflow/failure/conflict；关键行为断言、允许控制状态 patch、禁止关键结论、Citation 完整性预期；故障注入的时点/允许终态 |
| review / execution receipt | author/reviewer/裁决日期、争议、未审标签；运行后另存候选/模型/profile/Run 身份、实际快照/输出/trace/hash、分层分数/失败/缺失，不覆盖标签 |

多轮模式分开报告：**固定前缀 replay** 使用共同的人工编写 accepted 历史隔离选择/解释因素；**闭环 rollout** 每个 arm 建立独立 Conversation，只将本 arm 真正 accepted 结果传入后续轮次，检验错误积累。脚本为澄清预写不依赖候选措辞的用户回复分支；无适用分支记失败/未完成，不能临场为某 arm 帮答。每次重复从相同初始状态重新开始，不能复用前一 arm 的状态。两种模式不混为一个质量率。

| 必需类别 | 能区分策略的构造 / 预期行为 |
| --- | --- |
| simple follow-up | “另一种情况呢”沿用唯一明确任务，回答用当前 Evidence |
| pronoun/coreference | 代词绑定唯一有来源实体；近处干扰实体不靠 recency 获胜 |
| omitted entity | 补回省略实体/版本，只补用户已有意图 |
| old-but-relevant | 关键否定/条件跨无关 Turns 仍进入候选与最终必要组 |
| new-but-irrelevant noise | 与上一类配对只增加近期噪声；旧必要条件不被挤走 |
| topic shift | 独立新题停用旧 topic 假设，保留仍适用的显式会话约束 |
| topic return | 明示返回旧任务，找旧来源并应用其后纠正；不回滚 head |
| user correction | 新 Turn 更正旧实体或错误说法，保留旧记录但排除失效假设 |
| constraint supersession | “改为版本 B/不再限于条件 A”；恢复旧题也不复活已替代限制 |
| ambiguous reference | 多个同等适用实体或冲突前提，澄清并保持 unresolved，不做技术猜答 |
| no-rewrite-needed | 原文完整且无依赖；原文检索/skip 应保持质量并节省调用 |
| rewrite-required | 必要省略在原文无法独立检索；合格 Rewrite 有收益且无新增事实 |
| rewrite-danger / negation | 对照只改否定/version/time/条件，改写须保真；丢失并导致关键错答是 critical |
| document-scope change | 历史有证据但本轮排除；不得借历史扩大 scope；旧版本不自动映射新版 |
| evidence-insufficient | 意图可明确但当前 Evidence 不支持；正确不足/窄答，不引用旧答案作事实 |
| long conversation / context pressure | 必要组在窗口外；增加完整 pack/长条件触及预算，不能截否定/quote；不能装下时明确 overflow |
| single-turn regression | 自足独立题空历史，与 v0.1 固定同条件配对，原 Citation→Evidence→PDF 身份不变 |
| boundary/adversarial supplement | 历史错误答案/注入指令/撤权/缺源/失败草稿、取消与 stale 等不得进入 accepted 真相；技术语义与确定性故障分别打分 |

Split 角色：Calibration 只测量/基线方差及 rubric 可用性；Development 用于 E 系列调参和 Bad Case 分析；Regression 在候选选择后按固定协议确认，不用于参数选择；later-release confirmation 由维护者独立保管，在发布候选冻结后才开启。本轮后三者均未创建/封存，不称“Human Gold”。只有完成规定人类复核并记录 reviewer/范围的标签才可称 human-reviewed；AI 辅助标签保持 provisional。

按 entity/task/template/source family 做连通分组后再分配 split，成对 old-relevant/new-noise、同一对话改写和来源紧邻复述留在同 split；无足够独立族时声明限制并补原创材料，不能假称独立。现有公开单轮 regression 可作为已暴露的兼容守门，但不能当未见 confirmation。维护者不得通过旧 sealed 内容生成新多轮场景。

样本量/各层数量本轮 **TBD**；冻结时基于关键风险覆盖、独立族数、baseline 方差/目标不确定性与预算论证。关键轮次预先标记，包括所有可能触发零容忍语义边界的轮次，不可见分数后缩减。Development 和 Regression 有共同维度但不共享族。

## 4. 指标与分母

以预注册 target Turns 为计划人群 P，并保留所有重复。每个指标报告 planned、attempted、evaluable、missing/N/A 与原因；基础设施失败仍在完成率/工程成本分母中。没有结果不能当质量通过，没有适用实体/历史等不强塞 0 或 1。先按 scenario 聚合再按 primary_category 宏平均，另报 Turn 微平均及多标签分层；防止长对话支配总体。闭环后续未执行轮次计未完成并单列，不从 P 消失。

| 质量维度 | 定义 / evaluable population |
| --- | --- |
| coreference | 正确绑定数 / 有唯一 gold 绑定的引用数；另报 target Turn 所有绑定全正确率。歧义题在独立维度 |
| ambiguity / clarification | 应澄清题中正确澄清/该类全部计划题；不应澄清题中误澄清率；澄清内容是否指向缺失信息并保留 unresolved，不能只数问号 |
| Rewrite fidelity | 用于检索的改写中保留全部标注 intent assertions 的比例；分别报 negation/entity/version/time/scope 与无来源新增前提率。另报所有应改写题的正确解释完成率，避免靠全部 skip 美化 fidelity |
| topic shift / return | 应 shift/return 的轮次中活动/失效条目和来源全符合的比例；分项错误与混淆矩阵。无关旧假设进入关键技术结论归 critical |
| history candidate recall | 对每题 required groups G，候选里有完整等价来源组的个数 / G；空 G 为 N/A。分别报 A、B、union 去重前后；state 覆盖另列，不能把 state 命中伪装为 B 召回 |
| final history coverage / selection retention | 实际解释输入与生成输入各自覆盖 G 的比率；另报在候选已找回组中最终保留比例，区分 retrieval miss 与 budget/selection miss。通过 state 覆盖必须有原文 provenance，按 annotation 的允许等价关系去重 |
| intrusion / unnecessary history | 最终无关/禁止来源组数 / 最终全部历史组数，并报其序列化 tokens 占比；最终空历史分母为 0，N/A，不能称完美 precision。无历史需求题仍加入 history 的轮次/该类计划轮次单独报 |
| old recovery / new noise rejection | 旧必要组被 candidate/selection 恢复分别除以旧必要组；新无关组被排除数/预标新无关组。报告加噪前后的配对差异 |
| missed-history / supersession | 缺任何必要组的轮次/有 G 的轮次；被替代组错误激活次数/有 supersession 轮次；拆分候选、解释、最终组缺失 |
| correctness | 每个有输出且可判定的技术 proposition 相对原始材料和当前问题正确的比例；另报整题 correctness：全对/部分错误/关键错误。不能用“有引用”替代 |
| completeness | 支持充分且在范围内的 required aspects 已回答数/该题 required aspects；证据不足题按控制行为判定，不奖励编补缺口 |
| relevance | 回答中满足当前问题的内容单元/全部实质内容单元；题外事实即使正确也扣分。单元拆分规则/rubric 冻结 |
| evidence support | 当前 Evidence 实际蕴涵所附技术主张数/全部技术主张数；无引用或引用不支持的主张不通过；有效的替代原文支持允许人工裁决 |
| evidence-insufficient | gold 不足/部分可答题中符合 Feature 的不足或窄答比例；另报可答题误拒绝率，不能全部拒答得到高质量 |
| v0.1 / retrieval regression | 同 corpus/index/model/prompt/query 的固定 v0.1 与新空历史路径配对；排名/pack 身份与 scope 确定性一致性另验；改写导致 query 不同的效果归 Rewrite 实验而非擅改 ranking |
| physical Citation integrity | accepted 最终引用中正确解析到预期 Evidence/版本/span/PDF 的数/全部最终引用数，要求 100%；零引用分母 N/A，不赦免缺证据技术回答；损坏引用 accepted 次数必须 0 |

凡上表分母为“计划题”的行为完成率，失败/未输出不得算成功；有输出质量条件率同时报告，二者不可互换。细分指标缺少人工或有效 Judge 判定为 missing，不删除计划记录。声明权威事实检查依据是原始材料与 scope；人工 reference 不是唯一可能措辞。

工程成本独立于质量：每 Turn/Run/整会话的输入/输出 tokens（解释与生成分别；proxy 与 provider usage 分开）、调用数（尝试/派发/完成/UNKNOWN）、延迟（admission→durable final，另列首 delta、history PG、解释、检索、assembler、commit）、估计费用及 rate-card revision/实际 charge 可用性、candidate 每分支数、最终历史组/K/字节/tokens、state/pack/framing 占用、失败/澄清/overflow/显式 retry 率。均按全部 planned/attempted 与完成子群分别列分母；延迟报预冻结分位与超时截尾数量，不能丢超时。unknown usage/charge 为 unknown，累计预算保守预留；不以历史 Run 费用充当本次重评分增量费用。

## 5. 失败分类、标注和不确定性

| 类别 | 判准与处置 |
| --- | --- |
| critical | accepted Memory 升格 Evidence、关键技术错答因实体/topic/rewrite 漂移、无支持事实被宣布文档支持、Citation 身份损坏、越权/跨会话泄漏/静默扩大 scope、草稿 final、丢失/重复有效持久结果或 stale state commit。每类次数与案例必须报告，任何 accepted violation 阻断选型/发布 |
| material quality | 必要旧限制漏选、重要方面缺失、非关键错误绑定、错误拒答/澄清导致任务未完成；若导致上述关键技术错答则升级 critical |
| ordinary / recoverable quality | 非关键冗余、措辞或可恢复控制交互不足；不能把语义边界失败降为“风格” |
| infrastructure / execution | provider/PG 超时、连接失败、资源耗尽、中断、UNKNOWN；若已污染 accepted 真相同时标 critical |
| missing / non-evaluable | 缺记录、标签有争议、Judge 不可用、源材料不可核验；保留原因，不算通过，相关 gate 证据不足 |

多标签保留根因，主严重度按 critical > material > ordinary；execution 与 missing 作独立轴。已阻断的非法候选是 guard detection，不是 accepted violation，但计失败/完成率成本。later invalidation 不抹除曾被接受的 critical。

标注先于候选结果：人工检查关键实体/否定/scope/required groups/证据 locator，公开记录覆盖范围；AI-assisted 草稿不自动 human-reviewed。输出评审隐藏 arm 名称，随机排序，按同一 rubric 对所有 arm。Judge 只辅助，缺标签不从 baseline 标签推断；争议由维护者查看原文裁决，记录前后结果与理由而非直接改分。

Development 硬例/所有失败、Judge 分歧及候选 critical 输出须人工检查；Regression 和后续 confirmation 的全部预定义关键轮次、全部失败、分歧与零容忍案例由维护者复核。单维护者复核不宣称独立双盲专家集。无法复核时保持 incomplete。

配对比较只在相同 case/repeat/model/corpus/rubric 与控制配置上成立；先报全 P 完成率和每种缺失，再报双方均 evaluable 的配对 win/tie/loss/delta，列 unavailable pairs。N/A 不补成成功；可提供保守敏感性上下界但不替代主要分母。统计以独立 scenario family 为重采样单位，成对 noise/old variants 不拆开；cluster bootstrap 或小样本描述方案及置信水平在 comparison freeze 前选择，极少族时明确不支持精确区间。没有统计显著性不等于质量等价，使用预先接受的 material-similarity/noninferiority margin，绝不沿用未经论证的 -0.03。

## 6. 基线与共同控制

| Arm | 用途 / 限制 |
| --- | --- |
| V0 | 原 v0.1 代码基线及既有 profile/prompt 固定的单轮路径；与新空历史同条件配对。历史实际输出只有完整 receipt 可比时才引用，否则授权后重跑并标“重建 baseline” |
| R | Recent-Turn-only 简单对照：只用最近 N accepted Turns，不用跨窗 state 补漏、不用 B；共享解释/检索/assembler，评估简单窗口边界。它不满足已接受 A+B 产品方向，不能凭便宜被选为违反架构的首版实现 |
| A | recent + bounded structured state + deterministic filtering，无 B；隔离 state 的价值，与 A+B 比较 B 的增益 |
| AB0 | A+B 简单基线：已有 PG 元数据/显式来源检索、规则优先、精确来源身份去重、稳定来源 ID tie-break；自足 skip、必要时合并解释、无需时原文、无自动 refetch/修复、无 Summary。精确规则和 cap 在校准后冻结，不冒称已选中 |
| O diagnostic | 标注的最小相关历史/oracle 解释，仅用作 Development 定位召回/解释/生成瓶颈的上限诊断；不能作为可部署候选或总体胜率 |

所有 E 实验共同固定：数据/关键轮次/split/repeat，输入 head/state/source 版本，语料授权/index/bindings，retrieval ranking/pack/prompt，生成模型/采样/输出配置、tokenizer、环境与缓存条件、rubric/Judge、provider 速率/并发与总预算。除该行自变量外不得改动这些条件；不可避免变化使配对失效并记录。候选运行次序按预声明 seed 做交错/区组平衡，避免时间段/缓存成为 arm 优势；温度/seed 若 provider 不支持则记录 unavailable，用预定重复而非重试挑好答案。

## 7. 分阶段实验与消融矩阵

**Stage 1 — deterministic correctness**：不调用模型质量评测。用原创 fixtures、fake provider 和隔离 PG/必要的既有服务验证身份/来源/幂等、accepted 唯一、admission/commit 丢失、取消竞态、旧 fence、过期/重启 reconciliation、UNKNOWN、scope/引用/PDF、预算边界与旧 reader。记录失败、skips 和真实服务覆盖；mock 不能证明事务并发。任何失败先修正正确性，不能用 Stage 2 平均质量抵消。

**Stage 2 — Development screening**：下表每行必须继承第 6 节共同控制并增加行内控制；baseline/alternatives 在 calibration 后形成完整配置清单。质量选择均先过硬 gate，再遵循第 8 节 S（Pareto/非劣效）规则。不同 cap 的数值集合尚无证据，不在这里捏造网格。

| ID / 问题 | baseline → alternatives；自变量 | 行内额外控制 | 指标 / 类别 | 预期权衡、选择规则、重评触发 |
| --- | --- | --- | --- | --- |
| E1 候选来源 | R → A → AB0；history 来源能力 | 同 N/最终 K/history cap；state cap 在 A/AB0 同值 | candidate/final recall、missed、成本；old/noise/return | state 与 B 分开增量，不预设 AB0 分数；S 在合规 A+B 变体间选择；跨窗/词义 miss 重评 |
| E2 N/C 容量 | 校准出的最小可行 AB0 档 → 覆盖拐点档；分开改变 N、C | 固定检索规则/去重/最终预算；测 union/每分支 | recall、search_incomplete、PG 行/时延；old/long/return | 召回与 I/O；S，候选 cap 饱和或语料分布改变重评；N×C 只在校准揭示 union 截断交互时小型预注册比较 |
| E3 final K/history cap | 最小完整组档 → 额外上下文档；先各自单因子，再预声明小型 K×cap | 固定完整候选池、state、query/pack；排除实际输入相同档 | selection retention/intrusion、answer quality/tokens；old/noise/long | 多历史可能挤占必要组；S，无质量收益选小档；组长/输出成本变化重评 |
| E4 去重 | exact provenance ID → 同内容且同意图/scope 的来源合并、保留全部 provenance | 固定 pool cutoff 次序及预算；correction 组不可合并消失 | 唯一 required 覆盖、重复 tokens、supersession；correction/noise | 节省预算与合并错意风险；S，任何丢关键关系不合格；重复/版本分布变化重评 |
| E5 词法/元数据/排序 | 元数据匹配 + 显式引用规则 → 加词法分支；随后比较 entity/task/topic 优先规则，最后比较稳定 ID vs relevance 层内 recency tie-break | 分支读取 cap 固定；排序实验复用同候选；显式约束/修正硬规则固定 | recall、intrusion、old/noise、topic/negation；PG 成本 | 可解释召回与词面噪声；S，不将最新当相关；同义表达/同实体多任务误配重评 |
| E6 state/history 剔除 | 可选 history 先剔除 → 冗余 state 先剔除；另比较 state cap 档 | mandatory/完整 pack 不变，固定总输入余量；history cap 固定时先测 state | constraint fidelity、retention、overflow/tokens；correction/long | 冗余减少与丢有效条件；S，仅非必要项可变；state 增长/纠正链变长重评 |
| E7 输出/总输入 | V0 的 1024 仅为 output 对照 → 校准可行 reserves；固定 reserve 下比较 input cap 档，最后小型 reserve×input 交互 | 同选中候选/文档，记录实际序列化差异；不偷改 pack | completeness、length finish/failure、tokens/latency/cost/overflow；long/partial/compare | 输出完整性 vs 输入空间；S，tokenizer/model/答案任务改变重评 |
| E8 overflow | Feature 明确失败提示 → 更突出缩小范围或新会话引导；不自动变 scope | 构造同 mandatory 无法装入输入，固定错误类别与 state | 无调用/无 accepted、正确识别 overflow、用户按脚本恢复完成率；long | 不同提示可用性，不以容量拒绝充作质量 win；S，真实无法恢复案例重评；无交互测量则保留简单提示 |
| E9 skip / 激活条件 | 自足规则 skip + 依赖时 combined → 总是 combined 的诊断对照、保守 skip 条件变体 | 同 history、rewrite 使用规则及生成 prompt | interpretation/fidelity、false skip/false invoke、call/tokens/latency；no-rewrite/省略/shift/ambiguity | 成本 vs 漏依赖；S；always-interpret 仅诊断，不推翻架构自足 skip；依赖漏检重评 |
| E10 Rewrite 收益/漂移 | 安全原文检索 → 验证通过才用 Rewrite；rewrite-required 原文 arm 仅隔离诊断 | 同解释绑定、history、scope、retrieval 规则/模型；仅 retrieval query 变化 | recall/answer 与 negation/entity/version/time/scope drift；required/danger/no-rewrite | 检索收益与意图偏离；S，关键漂移否决；必要改写问题不能用原文 fallback 冒充产品可用；漂移或无收益重评 |
| E11 职责分合 | combined → 仅在 Dev 错误被定位后提议 separated 解释 | 新比较前冻结调用/延迟预算与 Feature/ADR 影响，其余同 E9 | 各解释子任务、call/cost/latency/failure；ambiguity/correction/shift | 更易定位可能昂贵；当前 deferred，Human Gate 后 S；只有合并职责瓶颈触发，不能见结果随意增调用 |
| E12 有限补取/修复 | 无自动补取/修复 → 定位到可恢复 candidate miss 后有界 PG refetch；模型修复另作为单独候选 | 在新轮比较前冻结触发/次数/总预算；UNKNOWN 永不重发，澄清行为固定 | 恢复率、critical、calls/PG 时延/成本；old/return/ambiguity | 修复收益 vs 循环/猜测风险；S，未消歧仍澄清；持续 miss 或费用失控重评；无证据保持 baseline |

不存在通用数值权重需求：E5 优先比较规则优先级；若后续提出学习权重，需新的、可辨别的比较协议。History/State/Evidence 不作任意六种排序，Evidence 契约不能被消融掉。E11/model repair 未经新 gate 不进入首版实现。

**Stage 3 — focused hard cases**：用冻结的 Development 硬例层（old/noise/return/ambiguity/correction/negation/long），同时看分类统计与具体 Bad Cases。只对 screening 剩余候选比较；若要加新案例或交互，先登记新的 dev/protocol revision 和剩余预算，再使用新结果。已预见交互优先为 K×history cap、reserve×input、candidate recall×选择；不做全笛卡尔积。报告 negative/无收益结果，不能只写 winner。

Bad Case 记录：case/arm/repeat、原文/scope、输入 state 和候选、缺失/多余来源组、解释/改写、最终 serialized context/pack、错误主张与实际引用、首个错误阶段、严重度、成本、是否存在 guard miss、仅改一个因素的下一次假设、待人审问题。首因区分 candidate retrieval → selection → interpretation → documentary retrieval → assembly → generation → validation/commit，不能统归“模型不够强”。

**Stage 4 — frozen Regression confirmation**：Development 按 S 选定后冻结代码/tree/config/prompt/data/metrics/protocol；运行一次既定 Regression 协议（含已预注册 repeats，不是挑最好一次），验证 v0.1 单轮、检索、引用/PDF 和全部硬 gate。任何失败保留报告，返回 Development；不改 margin、分母、题目、参数后反复跑到通过。必要修复形成新候选与新 protocol，已见失败集只可公开作回归重放，需另备独立确认材料；不能再称未见集。later-release confirmation 另需 release gate，本任务不打开它。

## 8. S：选择、记录与重新评估

先排除任何不满足硬不变量、资源上限、必需 trace 或确定性正确性的 arm；合规性不能折算成质量分数。再检查预冻结的关键分层质量、总体质量、完成率与 v0.1 非劣效。任何缺失关键人审或不可比较 baseline 均是 evidence incomplete，不可宣告 winner。

在可行候选中看 Pareto：critical-category quality、overall quality、v0.1 regression、tokens、latency、cost、复杂度、可维护/可追溯性。若一个候选在预定义容忍度内质量相当且成本/复杂度较低，选简单便宜者；复杂策略微小收益必须解释额外调用/失败状态/版本/恢复负担为什么值得。复杂度记录包括新增 provider phases、数据派生物、failure modes、配置面和诊断缺口；不为其编造一个综合分。存在不可支配权衡或区间无法判断则记录 inconclusive，由人审确定下一次有界测量，不按单最高平均分拍板。

每项决定必须落在本 Spec 的后续 decision record：问题/实验 ID、selected option、rejected alternatives、协议与精确配置/hash、全部指标与分母/Bad Case、人审证据、trade-off、remaining uncertainty、reevaluation trigger、批准人/日期。现在所有经验决策为 **UNSELECTED**，不预填胜者。

向量 Memory 的后续证据门槛：A+B 在足够来源存在时持续因同义词/词法或 metadata 漏关键旧组；O 诊断说明下游确实可用该来源；先与 PG/metadata 改进对照，在预注册质量/成本/延迟目标下仍不足，才提出隔离可重建 vector 方案的新 Spec/ADR，授权/失效/READY 不放宽。不是某个窗口失败就加向量。

Summary 的后续证据门槛：相关性与去重已改善仍频繁无法装入必要历史，或原文成本超过已接受预算；有原始来源的受控比较能保留否定、实体、时间、范围/纠正并减少成本，才提按需 summary。须保留原文/旧版本、fallback 与派生发布协议；不自动引入 Celery/滚动唯一摘要。二者本轮都 deferred，无获胜推断。

## 9. 审阅与限制

本包已有维度、类别、分母、baseline、消融、失败规则、冻结顺序与 Review 问题的明确归属，可进入 Human Feature/Evaluation Review。数据/数值/样本量/质量 margin/真实计量仍待校准，**不是可直接执行的已接受 Evaluation protocol**。下一任务须先批准校准方案并填冻结记录，然后才能授权业务实现和比较。

合成/原创小文档适合可控身份、否定、竞态和预算风险，不代表真实技术会话分布；公开可见 benchmark 有选择偏差，有限 gold 不穷尽合法支持；Judge 可错、单人复核不等于独立评审。离线 CI 验证现有工程，不是多轮模型质量或生产容量证据。本轮没有 paid/provider 调用、harness 实现、数据集封存或 release threshold 决定。
