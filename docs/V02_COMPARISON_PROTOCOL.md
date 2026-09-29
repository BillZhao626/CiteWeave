# v0.2 — Comparison Protocol Freeze Proposal

Status: **ACCEPTED — Human Comparison Protocol Review incorporated** · 2026-09-29

本次仅落实 Product Owner 的 **APPROVED** 决议。**Implementation NOT_STARTED；Comparison NOT EXECUTABLE；Provider/model/Judge 0 calls / 0 CNY；有限 CNY NONE/PENDING；baseline pilot NOT AUTHORIZED。** 协议接受不构成实现或任何 stage 的执行授权，不自动启动下一阶段。

Human Comparison Protocol Review：Product Owner 于 **2026-09-29** 在本次明确授权的对话中作出 **APPROVED**。审阅对象为基于 `96e8e584744a9e89f3d3566f1bbb5e694eb5c13c` 的未提交提案，原文件 UTF-8 字节 SHA256 为 `ef23a32d287d297dc362d1a1b4267ea3acdab976a93cd8927eb130eff4f9dc6a`；不虚构审阅 commit。接受记录随本次 coherent commit / PR 交付。

明确接受：N=2/C=8/K=2 仅为 first-slice 的 CONSERVATIVE_IMPLEMENTATION_DEFAULT，非实测最优、最终产品参数或 winner；DEFERRED / fail-closed 处理允许后续**单独授权**的 fake-provider/local L1 与结构性 v0.2a implementation，token caps/output reserve/真实 accounting/新 deadline/有限 CNY 在证据及独立授权完成前仍未冻结，对应真实 provider/candidate execution 禁止启动；DEV/HARD/REG 的 calls/review/engineering/runtime 只是未来最大边界；接受 V0→R diagnostic→A→AB0→hard→REG、E1/E8/E9/E10 active、E2–E7 deferred、E11/E12 triggered-only，以及 hard gates、描述性 paired comparison、zero-new-material-failure 与 Pareto 规则。有限构造集不代表生产总体统计结论。

以下保留原提案的设计论证和实质条款；“拟冻结”等原提案措辞按上述人审决议解释为已接受的设计/边界，DEFERRED 项仍未赋值，绝不解释为执行授权。不再做前置本地 Calibration。

目标是一个可工作、可追溯的 v0.2a：持久会话中的旧意图可恢复，技术回答重新取当前 Evidence，accepted result 与 state 只有一个有效真相。只实现一个 AB0 起点，不先造调参平台。继承 [Feature](specs/07_V02_First_Conversational_Slice.md)、[Evaluation](specs/08_V02_Conversational_Evaluation.md) 和 [ADR 0006–0009](README.md)；本文是 Evaluation 的具体冻结提案，不改其不变量、分母与长期决策。

## 1. 起点、证据与门禁处理

起始工作树干净，分支 `docs/v0.2-comparison-protocol`。HEAD 与本地 `origin/main` 为 `96e8e584744a9e89f3d3566f1bbb5e694eb5c13c`，tree 为 `28761b0adeccd079694f5f09bd467d66584d8e41`，即 recovery 收尾 PR #6。origin 为 `https://github.com/BillZhao626/CiteWeave.git`。本次 `git ls-remote` 连接重置，GitHub API 核验也不可用；不声称已在线确认最新 main。历史已记录且本地身份一致，远端不可用不阻止编写提案。

接受链：PR #3 接受 Feature / Evaluation 方法论 / ADR；PR #4 接受 Lean 最大资源框架；PR #5 的修订执行契约为 `7e0fc836d09ef6bd62759b5a1f9e58530eddaf73`，合并基线 `f66e7d94dd63b2597257dc7a0f5e267cb98c612f`；PR #6 收尾 recovery。已接受执行计划中的 NOT STARTED 是当时授权快照，当前完成状态见恢复收据与 HANDOFF，并无覆盖失败历史。

以下为本提案引用的全部本地测量证据，原材料仍 ignored，不纳入提交。只核对已有字节/收据，不运行计量器。

| 证据 ID | 精确身份与发现 | 能支持 / 不能支持 |
| --- | --- | --- |
| CAL | `.artifacts/v02-calibration/local-first-01-recovery-01/manifest.json` SHA256 `20656f0148a0adb5b9169f916fa9e916584e95b974b3df68cde99b6f36751062`；六族十 views；原失败批次保持不变 | 唯一 Calibration 身份；不能移作 Development / Regression |
| REC | 同目录 `local-receipt.json` SHA256 `43bd22fac56046ff9e5d929bb180f853fa76d55dc11ce22109f80ff6d825d6fc`；`report.md` SHA256 `8477ef5d4ae9267058122421c44c16e243248de83b33279c56a02494a9e94ee6`；index SHA256 `d67b6efa26f704339f0bf7e2699502dd47d771f46e4da90e2d8886009019bdb0` | 三文件、原四文件、public inputs 的 hash 均匹配 index；恢复 adapter 的 Git LF 内容 hash 为 `71b64157a4392e67c4d2de469b7cb18112d68ce8575eb6f6497decb698032013`，与收据一致。当前 checkout 为 CRLF，原始文件 hash 不同，不能把 checkout 字节称作执行原件 |
| H | index `human_review`：10/10、10 units、5 分钟，无未决争议；恢复新增 review=0 | F4.V1 是纠正前基线；manifest 中历史 PROVISIONAL 字段由后续真实人审记录解释，不能篡改为新审阅 |
| M01 | REC `targets.*.M01.groups`、`M01_family_distributions`：所需距离 1、2；F3.V2 旧题返回距离 2；F4.V2.G1 同含距离 2、1 | recent-1 不能覆盖这两项，B 与纠正整组有必要；不证明两轮之外无用，不估计自然尾部 |
| M03 | REC `targets.*.M03`：每 target 0–1 required groups；F4.V2 的一个组含两个来源；optional 均 0 | 整组不可拆、scope/version/negation/head/type/span/hash 与 provenance 边界；没有 optional 排序、C/K 最优值证据 |
| M04 | REC `targets.*.M04.envelopes`：解释 421–1691 bytes，生成参考 2243–3447 bytes；十 views 均适合本地工作量 | 只是参考封套；65536 bytes 和每族 16 Turns 只限本地工作量。不是 generation tokens、产品 byte cap、真实 pack/PDF 验证 |
| M07 | REC `targets.*.M07_pre.record_consistency`：十项 PASS | 静态标签契约；不证明实际无调用、事务、恢复或 accepted 唯一 |
| GAP | M02 SKIPPED；M05 unavailable；M06/M07-runtime deferred | 真实 tokenizer/reserve、PG 成本和运行时证据留真实切片；无新增前置 Calibration，无 provider pilot 或候选结果 |

**已明确接受的门禁处理**：Evaluation §1、Feature §7、Governance 的实现前 Human Gate 已由本次 Product Owner 决议完成。无证据的容量不填任意正数，相应运行路径保持 **disabled / fail-closed**，后续数值绑定规则不变。DEFERRED 项不阻塞后续单独授权的结构性实现与 fake-provider/local L1；本次仅记录接受，没有授予该实现或 L1 执行权限。

真实生成与候选比较须在同一协议的执行记录中先补全精确数据字节、实现/prompt 身份、verified accounting、容量、期限与有限预算并经 owner 接受，再单独授权执行。补全依据只能是下面预定的规则、官方身份和真实 L1/固定参考计量，不能看候选答案后反推值。需要模型输出证据才能决定的 reserve 继续 DEFERRED，另提最小有界 provider 授权；本提案不自动授权该 pilot。无需另立治理文档或重开本地 Calibration。

## 2. 数据、配对与 rubric（D-DATA）

冻结的是下列小规模构造规则和 ID 槽位；**Development / Regression 尚未物化、未封存、非 Human Gold，字节 hash 为 DEFERRED**。独立授权后先制作、人工核验标签并保存 manifest/hash，再运行任何候选；不得以本表冒称完整数据已存在。理由：六种独立风险可支撑有限集合诊断，无方差证据支撑总体推断；不为统计功效扩样。沿用 Evaluation §3 schema，记录原文、作者/许可/AI-assisted、scope/不可变材料/span/PDF、来源图、行为断言、允许等价类和 review。

| Development family / 两个固定 target views | 必须区分的行为；配对只改所列因素 | hard subset / critical targets |
| --- | --- | --- |
| D1 / V1、V2 | 唯一实体指代/省略；V2 增加近期无关实体，使必要来源在 recent-2 外 | V2：old、noise；两项均检查绑定与 Memory/Evidence |
| D2 / V1、V2 | 自足空历史题；V2 加入无关旧话题，原问题不变 | 两项检查 skip、shift、单轮污染；非 hard 主层 |
| D3 / V1、V2 | 回到旧任务；V2 加一次明确纠正，完整纠正链不可拆 | 两项：return、correction；均 critical |
| D4 / V1、V2 | V1 两个同等适用实体需澄清；V2 明确其中一个，需正确解除 unresolved | V1：ambiguity；两项检查控制结果与有效状态 |
| D5 / V1、V2 | 只改变否定/version/time 断言，当前 scope 不扩大；至少一项需保真 Rewrite | V2：negation；两项均 critical |
| D6 / V1、V2 | 同一问题缩小 scope，V2 当前 Evidence 不足；同 payload 另做 token L−1/L/L+1 确定性边界 | V2：pressure、scope；两项均 critical，容量与证据不足分开 |

DEV 固定 6 families / 12 views，hard 是其中 **D1.V2、D3.V1、D3.V2、D4.V1、D5.V2、D6.V1、D6.V2** 七项，不另采族。D6.V1 补足同完整 pack 的容量对照。所有 12 项均登记 critical assertions，普通输出质量另评分；不能为节省人审事后取消 critical。另在 L1 原创故障 fixtures 覆盖 boundary/adversarial、实际超窗和真实容量失败，不算新的模型样本。必须逐项映射 Evaluation 的十八类别，未覆盖项显式 incomplete，不能用类别名称代替原文标签。

REG 拟固定独立 G1–G6 / 每族两 views，共 12 targets，风险分工同上；另有 6 项 V0 单轮配对，取各族预登记的自足 view（G1.V1…G6.V1，原文须足以独立回答），合计最多 18 个执行槽。G 的第二 view 承担该族多轮/歧义/范围风险。所有 critical 与失败必审。Product Owner 保管 G 原文/标签；在唯一候选 code/tree/config/prompt/data/rubric 冻结且 DEV/HARD/L1 通过后，由 owner 显式开启一次。旧公开单轮 regression 仅作已暴露兼容检查，旧 sealed 内容不读；later-release confirmation 不开放。

CAL、D、G 按 entity/task/template/source **连通族**隔离；风险类别可相同，不能复用同一对话模板换名冒充独立族。原文制作后先审查连通性，不够独立就标 INCONCLUSIVE，停止比较而非挪动见过的题。所有衍生/加噪/纠正配对留在同族同 split。材料 hash 缺失不阻止审阅提案，但阻止任何候选执行。

Rubric=`comparison-descriptive-v1`（本文及 Evaluation §4–5 的接受版本共同构成身份）：每个 assertion 记 correct / incorrect / missing / N/A，证据为原始材料和当前 scope；整题 correctness 为全对/部分错误/关键错误，完成状态单列。required aspects、技术 proposition、实质内容单元均在盲审时按最小可独立判真的主张拆分；标签预列必要方面及允许替代证据，不能按某 arm 措辞重定义单元。严重度沿 critical > material > ordinary，execution/missing 独立轴。reference 不限定唯一措辞；合法替代支持经盲态人工裁决，留下旧标签及修订理由，影响判定则对所有 arm 同样重评，不挑受益 arm。

计量单位为预登记 target execution，`P=全部计划项（含 repeat）`；配对键为 family/view/mode/repeat/model/corpus/rubric/控制配置。默认 repeat=1，是预算受限的描述性选择，不声称模型稳定。固定前缀 replay 与闭环分报，闭环每 arm 独立 Conversation，预写澄清回复分支，未执行的后续项保留在 P。先 scenario 再 primary_category 宏平均，另报 Turn 微平均及多标签层；不把同族两个 views 当独立样本。primary_category 随 manifest 在结果前固定；未知方差只限制结论，不触发临时 repeats。

数据重评触发：许可/身份错误、连通族泄漏、必需覆盖缺失；先停，形成新版本并审阅，不追加 Calibration 或在原结果上重划 split。

## 3. Arm 与精确身份（D-ID）

| Arm | 状态 / 唯一比较身份 | 可改变的决定 |
| --- | --- | --- |
| V0 | **EXISTING_V01_CONTRACT**：发布提交 `d29a324a06c07799a11ed642e370c5e6d5a2e6db`，本次基线 HEAD 的产品 `src/prompts/alembic` 与其无 diff；无会话 profile。主对照显式选 `telecom-structural-v1`；旧默认 `m3-context` 另作兼容保护，不与 structural 混算 | 空历史路径是否保持旧行为；不是多轮候选 |
| R | **DESIGNED / TO_BE_IMPLEMENTED**；`cp-r-v1`，N=2，仅 recent accepted history，无 state/B；其余与 AB0 相同 | 只作来源诊断，不能选为产品 |
| A | **DESIGNED / TO_BE_IMPLEMENTED**；`cp-a-v1`，N=2 + bounded state，无 B；其余与 AB0 相同 | 隔离 state，及 B 是否改变候选/最终来源；不是替代已接受 A+B 的产品方向 |
| AB0 | **DESIGNED / TO_BE_IMPLEMENTED**；`cp-ab0-v1`，本节共同身份 + §4 唯一配置；不是已赢的 arm | 首版唯一可部署设计起点；证据不合格则修复/不晋级 |
| Oracle | **DESIGNED / TO_BE_IMPLEMENTED，TRIGGERED_ONLY**；`cp-oracle-diagnostic-v1`，人工最小完整历史/解释 | 仅在 DEV 定位“来源找回后下游是否能用”；默认执行额度 0，永不产品候选、永不总体胜率 |

V0 原 tree 为 `259f6721467556388116623609a3c8265607eb16`，`apps/web` 同样与基线 HEAD 无 diff；新 arm 实际 code/tree SHA、serializer/prompt 文件字节、依赖 lockfile 与执行入口 hash 均 **DEFERRED_UNTIL_REAL_SLICE**，在第一次执行前绑定一次，不能以设计 ID 冒称代码已存在。每个 Run 保存可恢复内容与 hash，不仅保存可变文件名。

固定现有 answer 模板：`prompts/answer-telecom-v1.txt` SHA256 `4229c840f98099dc4d084a5898f51f45846c644866c787e030925997ddf6a14d`；旧默认 `prompts/answer-v1.txt` SHA256 `6956bb795ecbc59114a58b06f7af0dd64c62b6e4be630c4e50b4ddf1bf0873d3`。新增 combined interpretation 与会话 framing 字节在实现后、任何输出观察前冻结；不修改既有 answer 文件。产品 retrieval ranking、pack、offsets、Dense/BM25/RRF/BGE 路径不变。

模型/provider/revision、采样配置、真实 tokenizer/accounting revision、官方规格/rate-card、corpus/DocumentVersion/canonical/PDF hash、READY index/binding/scope 快照全部 **PENDING**，本次不读取运行库或凭据。执行 manifest 必须同时绑定这些项及 stage/arm/Conversation/Turn/Run/attempt 账本、协议 SHA、环境/缓存条件。不可固定 alias revision 则标限制并由 owner 接受，不能称严格模型可重复。新旧 arm 同条件重建 V0 才可比，不引用无完整 receipt 的历史成绩；旧估价 `deepseek-flash-CNY-2026-09-13` 不作为当前支付凭据。

依据为既有源码身份、Evaluation §6 / ADR 0009；选择可解析 hash 是为避免默认漂移。实现字节/模型可用性仍未知；任何身份变化使原配对失效，先新版本冻结，不能混用结果。

## 4. 首版参数与有界算法（D01–D12）

标签缩写仅用于本表：**CALIBRATION_DERIVED**=构造集/人审支持；**CONSERVATIVE_IMPLEMENTATION_DEFAULT**=有限可实现默认，未测最优；**EXISTING_V01_CONTRACT**=既有控制；**DEFERRED_UNTIL_REAL_SLICE**=当前不赋运行正值。结构不变量直接继承 Feature/ADR，不是经验选项。每行同时给出理由、未知和触发。

| 决定 / 拟冻结值或规则 | 来源标签 / 证据与理由 | 不确定性 → 重评触发 |
| --- | --- | --- |
| D02 N=2 accepted Turns，只控制 A，B 搜索全会话可定位历史 | CONSERVATIVE_IMPLEMENTATION_DEFAULT；M01 的距离 1/2 只提供最小起点动机。绝不把 2 当 useful history 上界 | 自然长尾未知；超窗 miss 先定位 B，不自动加 N |
| D02 C=8：A/B union 精确去重后的完整来源组上限；D03 K=2：最终完整来源组上限（解释与生成分别记录） | CONSERVATIVE_IMPLEMENTATION_DEFAULT；M03 只支持至少可容一个双来源组，8/2 均非实测拐点。只设一档，无网格 | 多必要组分布未知；mandatory >C/K 时明确失败，不截组；真实 cutoff/selection miss 才提单因素新协议 |
| D05 B 最多四分支：显式 Turn/source 引用、实体+有效约束、task、topic；都先过滤 conversation/当前授权/head/accepted | CONSERVATIVE_IMPLEMENTATION_DEFAULT；Feature §4、M01。PG 元数据精确匹配，未解析/不唯一保留歧义；不做 embedding 或词法扩展 | 同义表达漏检未知；真实可定位来源 miss 才触发 E5 |
| D05 排序：先 mandatory/明确引用及纠正关系，再 entity+适用约束、task、topic；同一相关层按稳定 source ID；recency 不额外加权 | CONSERVATIVE_IMPLEMENTATION_DEFAULT；ADR 0008。A 的 recent 来源同样须证明相关，不能凭新近入选；每分支先取最多8组候选，再统一去重/排序/C cutoff | 规则泛化未知；同实体多任务误配或规则并列才重评 |
| D04 精确来源 ID 去重；同一 provenance 重复引用合并，保留全部边；相同文字不同 scope/version/negation 不合并 | CALIBRATION_DERIVED；M03 F4 + ADR 0007；模糊/语义合并=0 | 没有冗余成本证据；重复负担影响可行输入才触发 E4 |
| D03 纠正/supersession/必要否定组成原子组，保留被替代原文和边但不激活旧假设；只新 Turn accepted 后发布新 state | CALIBRATION_DERIVED；F4.V2 的 [2,1] 链与 M07。state 命中须回链完整可验证原文，不能伪作 B 召回 | 链更长或纠正对象不明 → 澄清/失败；不静默丢早期成员 |
| D06 state 的本 Run 投影最多16条；每来源组最多8个原文成员；整组按身份顺序输出 | CONSERVATIVE_IMPLEMENTATION_DEFAULT；为有限物化和诊断，不来自16-Turn工作量上限；数字16不限制会话长度。必要条目不能裁掉，持久 snapshot 不截断 | 真实 state/组规模未知；越界失败并记录，L1 或实际来源结构触发新协议 |
| D02 history 阶段总上限：最多8次 PG round trips、64个物化原文来源行（含关系展开）、128 KiB UTF-8 读取 payload；每分支最多8组 | CONSERVATIVE_IMPLEMENTATION_DEFAULT；M06 缺失，先设可测试保护；计 A/state provenance/B/链，不能用分页绕过累计上限；sentinel 行也计数 | LIMIT 不证明 rows examined 有界；索引访问/扫描行上界与 statement-time 为 DEFERRED_UNTIL_REAL_SLICE，真实查询准入前由计划/资源证明补齐，否则该查询 disabled；不许可全库扫描 |
| D09 skip：原问题自足、无指代/省略/待澄清/有效 state 冲突、无需旧约束补全时确定性 skip，记录理由；不能确认就 combined interpretation | CONSERVATIVE_IMPLEMENTATION_DEFAULT；M07 F1/F2/F5 只给标签例子。topic/coreference/query 共享最多一次解释；不确定实体不猜 | 语义漏检未测；false skip/误澄清 → E9，新条件须新版本，不启用 always-interpret 产品 |
| D10 原文可安全独立检索则用原文；依赖补全确有来源且 fidelity 验证通过才用 Rewrite；否定/entity/version/time/scope/条件不可变 | CONSERVATIVE_IMPLEMENTATION_DEFAULT；Feature §4、M07 F6。关键漂移阻断；安全原文才 fallback，否则澄清/失败 | 结构 guard 不证明语义保真；人工漂移或无收益才触发对照 |
| D06 Assembler 固定顺序：现有系统模板/策略 → 原始问题与显式限制 → 已验证解释与必要来源组 → state 投影 → 其余 relevant history → 完整本轮 EvidencePack；Memory/Evidence 类型隔离 | CONSERVATIVE_IMPLEMENTATION_DEFAULT；Feature §5。Evidence 内部顺序、标签、pack 不变；去无关/失效后先逐组去可选 history，再去冗余 state，每次重计完整消息 | 当前无 optional 组效果证据；真实压力才触发 E6；mandatory/pack 从不参与裁剪 |
| D06 序列化：UTF-8/LF、稳定字段与数组顺序、JSON 不转义非 ASCII，明确 source type/身份/span/hash/适用条件；保存原文字节及 serializer revision、实际 input 和 output snapshots | CONSERVATIVE_IMPLEMENTATION_DEFAULT；M04 展示 framing/escaping 不能忽略，ADR 0009 要求重建。计量参考 envelope 不冒充最终 messages；原文不归一化改 offsets | prompt/framing 字节待实现；任一变化重计完整输入并更新身份 |
| D12 自动 retry=0、refetch=0、模型修复=0；每 Run 最多解释1次+生成1次；显式 retry 每 Turn 最多1个新 Run且仍满足原 head/scope/无accepted前提 | CONSERVATIVE_IMPLEMENTATION_DEFAULT；Feature/ADR 0006 保留显式 retry；比较运行显式 retry=0，产品两 Runs 共最多4次发送；UNKNOWN 不重发 | 新缺口不自动扩额；仅 E12 人审触发可讨论 PG 补取，模型修复另审 |
| D07 期限：旧 generation 35s、transport 25s 及更严格现有 deadline 保持；新会话 Run/Conversation、PG statement/reconciliation 期限不套旧60s默认 | EXISTING_V01_CONTRACT / DEFERRED_UNTIL_REAL_SLICE；无 M06/runtime 分布，新组合期限须真实路径验证、候选输出前冻结；未绑定期限不启动对应执行 | 不能拿 campaign 45s 绝对取消界当产品 SLO；L1 故障路径证明有界后绑定 |

materialization cap 超限记录 `search_incomplete` 和 cutoff 原因；明确引用/适用约束等 mandatory 来源恢复不完整时禁止技术答案，真实歧义才澄清，否则失败。检索遗漏仍可发生，不能声称 selector 自动知道 gold required groups。L1 与 Evaluation 分别检测 guard 行为和未被识别的遗漏。

## 5. Token / 容量与 accounting（D07）

**DEFERRED_UNTIL_REAL_SLICE**：history/state/generation/interpretation token caps、两阶段 output reserves、模型 context/output 上限、产品 Conversation 累计 tokens/CNY/时长。byte/码点和 BGE proxy 均不换算 generation tokens；旧 `1024` 仅 V0 的既有输出对照，不能选作会话安全 reserve。

拟冻结的绑定程序（依据 Feature §5、M04/GAP；未知为真实模型表示，触发为 serializer/model/容量变化）：

1. 执行授权前记录官方 provider/model/revision/context/output 限制、来源 URL/访问时间/内容 hash；tokenizer 名称、版本/词表 hash、库版本、chat template/message framing/accounting revision 必须匹配所选模型。无法验证完整 framing 或有依据的保守上界，provider 发送保持0，不报告 ready。
2. 对**实际发送的完整 serialized messages**计量，包含 system、角色、标签、转义、元数据、分隔符、原文、state、history、完整 pack；解释/生成独立计量。分组件只作归因，不直接相加当总数；保存完整数、组件数及差额。provider usage 与离线计量分列，冲突先停，不覆盖计量。
3. 在任何候选输出前，用固定、人工核验的参考 answer/clarification/interpretation JSON 和实际 serializer 求真实 output tokens。由 owner 依据参考最大完整输出、官方输出上限、输入余量和有限费用选定一个 reserve 及余量理由，并预登记 length/finish 检查。参考最大值不是生成完整性保证；无法论证余量时 reserve 仍 DEFERRED，只有单独授权的固定基线证据可解锁，不能边看 AB0 输出边加倍。
4. generation 满足 `tokens(full messages) ≤ min(input_cap, model_context_limit − output_reserve)`，解释独立同式；组件 caps 与整体预算同时满足。任何 mandatory/完整 pack 装不下，剔除全部可选项后仍超界则 overflow-failed：无回答调用、无 accepted state、保留原输入/失败 Trace，提示缩小问题/范围或新会话。绝不自动改 scope 或伪装 Evidence 不足。
5. 未验证计量/期限/预算是 `accounting-unavailable`，与真 overflow 分开；产品付费路径 fail closed。fake-provider L1 可注入明确的测试容量验证边界，但不能把 synthetic tokenizer 的通过写成真实 accounting VERIFIED。每次调用须先持久预留；缺 Conversation 总额亦不得派发，不能新 Run 绕过累计额度。

## 6. E1–E12 与最小执行序列

ACTIVE_FIRST_SLICE 只表示首片必须核验的决定，**不授权现在执行，不等于每行各跑付费实验**。共同冻结 §2–5 全部非自变量；实际输入相同则复用同一 receipt，不重复生成。观察点只在 DEV 前6项配对、DEV 全12项、HARD 全7个 target 结束；硬违规/预算/UNKNOWN 可随时停。DEV 按 D1…D6、V1后V2；同一 pair 的 arm 顺序按 family 奇偶交替 A→AB0 / AB0→A；固定前缀隔离，repeat=1。抽样/盲审 seed=`20260929`，排序为 SHA256(seed、stage、family、view、arm、repeat)，保存顺序；执行顺序与盲审显示顺序分别记录。

| E | 分类 | 本协议的值/arms 上限、能改变的决定；再开启条件 |
| --- | --- | --- |
| E1 | ACTIVE_FIRST_SLICE | 本地 R/A/AB0 ≤3 arms；后续 paid 仅 A/AB0 ≤2。定位 state/B 增益或 miss，不选掉 A+B；来源/输入完全相同就停止重复 paid |
| E2 | DEFERRED | N=2/C=8 单点，正确性和成本仍测；仅真实候选饱和/cutoff miss 才提 N 或 C 单因素 ≤3值 |
| E3 | DEFERRED | K=2 单点，mandatory retention 必验；真实 selection miss/组规模增长才提 ≤3值，不做 K×cap 网格 |
| E4 | DEFERRED | exact provenance 单点；身份契约必验；有实际重复 token 压力且可保真才提 ≤2种去重 |
| E5 | DEFERRED | 四分支/规则优先单点；真实同义/metadata miss 或误配才提 ≤2 selector；先同池本地定位 |
| E6 | DEFERRED | 可选 history 先剔除单点；保全 mandatory 必验；仅真实不同投影可改变完成率才提 ≤2次序 |
| E7 | DEFERRED | accounting/容量绑定为真实生成前置条件；没有数值 arms；有固定基线容量证据才提 ≤3 reserves，input 单因素另批；不猜值 |
| E8 | ACTIVE_FIRST_SLICE | 一个 overflow 行为，L1 确定性验收，paid=0；无交互证据不比较文案；只改变失败路径是否合格 |
| E9 | ACTIVE_FIRST_SLICE | 一个 skip+combined 策略，复用 E1 receipts/人工标签；决定 false skip 是否需修复，无 always-call 新 arm |
| E10 | ACTIVE_FIRST_SLICE | 一个“安全原文/验证后必要 Rewrite”策略，复用同批；决定 drift 是否阻断；原文诊断备选最多2 arms须另登记，仅可用剩余同账槽位 |
| E11 | TRIGGERED_ONLY | 当前0 arms/0调用；明确合并职责瓶颈且诊断可区分原因后，另经 Feature/ADR 影响人审，最多 combined/separated 两臂 |
| E12 | TRIGGERED_ONLY | 当前无 refetch/repair；证明可恢复 candidate miss 且下游需要后，另审 no-refetch/一次有界 PG refetch 两臂；不夹带模型 repair |

顺序固定：**V0 身份/单轮 L1 → R 本地诊断 → A → AB0 → hard → 唯一候选 REG+V0**。第一轮没有第二个合规产品候选，不为选“赢家”造变体。AB0 不合格则返回修复；A/R 较便宜不是删 B 的理由。Oracle 默认0；只有已有 DEV 首因无法区分 candidate/interpretation/generation 时才提出限定 case、预算及新版本，结果只定位瓶颈。Summary/vector Memory 的 accepted trigger 尚未满足，均不激活。

任何新 arm、值、case、prompt、阈值或预算扩展必须在新结果前修订本协议并独立获批；已见数据标为 Development，不能用新阈值回头宣布旧比较通过。剩余额度不是实验授权。

## 7. 硬门禁、质量与有限集合决策（D-QUALITY）

硬门禁优先：accepted Citation 物理解析 **100%**；accepted critical Memory→Evidence、cross-scope/conversation 污染、stale accepted、多有效结果/Turn、关键 entity/version/negation/scope Rewrite drift **各为0**。同样禁止草稿 final、关键 topic 漂移和无支持主张冒称有文档支持。guard 阻断单列为 detected failure，不能混成 accepted violation 或成功。怀疑即暂停，人工确认违规立即停止该 arm；later invalidation 不抹历史。

| 指标（沿用 Evaluation 术语） | 冻结分母与报告方式 |
| --- | --- |
| required candidate recall | 完整等价 required groups 命中/G；A、B、union 去重前后分列；state 覆盖另列 |
| final required-source coverage / retention | 解释、生成各自覆盖/G；候选已命中的完整组最终保留数/候选已命中组数；区分 retrieval 与 selection miss |
| irrelevant-history intrusion | 最终无关/禁止组/全部最终历史组，另报 serialized token 占比；无历史需求却加 history 的题/该类全部计划题 |
| old-history recovery / noise rejection | candidate 与 final 恢复的旧必要组/所有旧必要组；排除的新噪声组/预标新噪声组；报告加噪前后配对差 |
| correction/supersession、shift/return | 适用目标中全部活跃/失效来源及状态正确的目标数/该类计划目标；另报错误激活 superseded 次数与 missed-history |
| coreference / clarification | 正确唯一绑定/全部唯一绑定；应澄清题正确澄清/该类计划题；不应澄清误澄清率；全绑定正确与 unresolved 分列 |
| Rewrite fidelity | 实际检索改写保留全部 intent assertions/全部实际检索改写；按 entity/version/time/negation/scope 分列；另报应改写题正确完成/该类计划题与无来源前提率 |
| Evidence support、correctness/completeness/relevance | 当前 Evidence 蕴涵主张/全部技术主张；原材料可判 proposition 正确率、整题三档；回答 required aspects/可答 required aspects；相关实质单元/全部实质单元。引用合法不等于支持 |
| Evidence 不足、完成率 | 正确不足/窄答/对应全部计划题；可答误拒绝率；按 gold 行为正确完成/P，execution 失败不消失 |
| v0.1 regression | 同模型/query/corpus/index/prompt 条件下 V0 与新空历史配对；确定 ranking/pack/scope/Citation→PDF 身份一致性另验；不同 query 的效果归 Rewrite |
| Citation / 成本 | 可物理解析引用/全部 accepted 引用；零引用=N/A，损坏 accepted 次数必须0。cost/usage/calls/UNKNOWN、admission→durable final、各阶段、读取量、overflow/retry 按 planned 与完成子群分别列 |

所有 G/历史/引用分母为0记 N/A，不补成成功。每项同时报 planned/attempted/evaluable/missing/N/A；缺 review、执行失败、停止后的未执行项保留原因。有输出条件质量与全部 P 完成率分开。延迟仅报 min/median/max 与 timeout 截尾数，不估总体 p99。MRR 只作 documentary retrieval 诊断；没有 generic weighted score。

**阈值是预先选择的风险规则，不是 Calibration 测出的胜率**（CONSERVATIVE_IMPLEMENTATION_DEFAULT；依据小样本/无 M05 方差与 Evaluation S；触发为新任务分布或完整证据仍无法判决，须新协议）：

- 本有限计划内，critical assertions 必须全部正确且完成人审；hard 七项必须按 gold 完成，缺 mandatory 来源、错误拒绝/澄清或 overflow 冒充不足均不通过。真实 gold overflow 的正确失败计行为完成，不计技术回答成功。普通项出现 material 错误不晋级；这不是生产100%可靠性声明。
- 配对先报各质量维度 win/tie/loss/delta 和 unavailable pairs。**非劣效 margin=0 个已标注 material/critical assertion 的新增失败；完成率不得降低；v0.1 确定身份差异=0。** 不继承历史 −0.03。普通措辞差异仅在原 rubric 已标 ordinary、且不改变任何上述质量主张时可视为 tie。
- material similarity 要求相同有限配对人群上所有 critical/material assertions、gold完成行为、必要来源覆盖结论均相同，且每个适用质量比例不下降；不以“没有显著性”推等价。更多 irrelevant history 不算收益。未审输出不能声明相似。
- Pareto 在合规候选内逐维比较质量、调用/tokens/实测延迟/费用及新增 phases/派生物/失败模式/配置/维护负担。相似时优先少调用、少 tokens、少复杂度；这些维度互有取舍且无预定支配关系则 INCONCLUSIVE，不能临时加权。仅延迟微差不独自定胜负。
- dominance：所有计划配对及关键层均完整可评且不差，至少一个质量或成本/复杂度维度严格更好、其他维度无反向优势，才可宣布本有限集合支配。R/A 不成为合规产品候选。
- futility：在三个预定观察点，对每个维度的缺失项分别填最有利/最不利合法结果；即使全部余项最有利仍不能满足上述零新增material失败/完成率门槛，且不存在相似但更便宜的路径，则停止。不能安全给界就预算止步 INCONCLUSIVE，不能凭均分低提前淘汰。
- 无统计检验、无 bootstrap/置信区间、无总体非劣效声明；六族只支持有限集合诊断。标签争议、关键缺失、模型身份变化、预算耗尽、未覆盖层或不可支配取舍均 INCONCLUSIVE；不能临时增 repeats 消除不确定性。

## 8. 未来预算与人审（D-BUDGET / D-REVIEW）

当前全部执行额度为0。下表是拟冻结的后续最大范围，均在已选 Lean 内，须逐 stage 另行授权；CAL 已退出，RES=0，Judge=0，cloud/GPU租用=0。上限不是目标。所有确定性 R/A/AB0 诊断在 DEV 本地池内，不增加 paid arm。

| Stage | 最大 arms / executions（repeat=1） | 最大 physical calls | 人审 units / minutes | 评测工程 / local runtime / execution elapsed 上限 |
| --- | --- | --- | --- | --- |
| DEV（含真实 L1、L2、L3） | 本地≤3，固定12 views×3≤36 target replays，每个冷/热各一次最多72；paid A/AB0≤2，12×2=24 executions | 48=24×(解释1+生成1)；skip 省下不另花 | 48 / 384；12 labels+24 outputs=36，余12争议/复核 | 6小时 / 60分钟 / 153分钟（setup30+recovery15+local60+48 slots） |
| HARD | 默认 AB0 一个配置；七 hard target，每项最多一个真实前驱+target，最多14 executions，独立会话闭环；其余共同初始前缀固定 | 28=14×2 | 28 / 224；labels沿用DEV，最多14输出，余14复核 | 2小时 / 30分钟 / 83分钟（15+10+30+28） |
| REG | 唯一 AB0 + V0 兼容参照；12 targets+6单轮baseline=18 executions | 30=12×2+6×1 | 36 / 288；12 labels+18输出=30，余6复核 | 2小时 / 30分钟 / 85分钟（15+10+30+30） |

HARD 只检验一段真实前驱→target 的累积效应，不声称从空会话全长 rollout；需要更多前驱时该 case incomplete，不暗中增加执行。每个前驱、澄清回复、失败、baseline 重建、proxy 与诊断均占相应槽，不能只计目标答案。合计 paid 上界106 calls / 56 executions、人审112 units/896分钟、评测工程10小时、local120分钟；这是上限算术，不是已授权消费或生产成本。产品实现工时不从评测工程池支取，另行实现授权须给有限工程 cap；本提案无隐藏实现额度。

时间继承 Calibration Plan §8.2 的串行一次真实 attempt 外层≤45秒绝对取消界、每slot预留1分钟；旧生成从严受35s/25s/Run期限约束。campaign elapsed 包含执行等待、失败和对账，不把人审/产品工程小时伪装为该 elapsed；其分别受上表 minutes/hours 硬限，跨重启不重置。新增解释路径若不能施加期限则不启动。这些是 campaign 安全上界，不是测得产品 SLO。

local PG 全 stage 数量按 `Q≤2×T_local×A×8`（T_local 是固定 view/执行槽数，A 是本地配置数）取启动登记中的更小实际列表；DEV 的72次冷/热 replay 已含 A≤3，不再乘3，故候选 history round trips 上界576。每次 history 读另服从 §4 rows/bytes/round-trip cap；rows examined、statement-time 未绑定则不准入真实候选查询。L1 为解除该缺口，可在独立实施授权中先登记测试专用有限数据/扫描/期限边界，在隔离 PG 测真实查询；这些测试值不冒充产品参数，不使用候选模型质量结果。故障/并发测试按 §9 固定矩阵登记，不是任意追加 replay。

未来 tokens/CNY **PENDING**：每 phase 真实 `I_p/O_p`、官方非缓存最坏适用单价/币种/税费等核实后，逐 attempt 计算 `I_p×input_rate + O_p×output_rate`（按官方计费单位换算并包括其他适用项目），累加到 Run/Turn/Conversation/arm/E/stage/campaign 及既有全局月预算。有限 owner CNY ceiling 与已核验余额共同限制；任何一项未知不派发。Conversation 上限按其冻结脚本内全部 Turns/前驱/retries 求和，产品一般会话额度仍 DEFERRED，不能用比较脚本预算替代产品参数。

retry allowance：比较额外重试0、refetch0、Judge0；原子预留 calls/tokens/最坏费用及 review 容量后才发送。UNKNOWN 保持最坏占用，最多一个 unresolved 即暂停全 campaign 新派发；限 recovery 时间对账，不能解决就结束 INCONCLUSIVE，不换 Run 重发。任何资源先到、硬违规、hash/身份不一致或输入相同无新决策价值立即停；余额不跨 stage，不自动动用 RES。

必须人工复核：所有 critical 输出、guard failures、所有失败、hard、影响选择的 Judge 分歧（未来若另授权 Judge）、REG critical/失败/分歧，及每主要失败类至少一个代表 Bad Case。标签 review 与输出 review 分开计 unit，重复复核另计；5分钟历史审阅不能当未来每unit时长证据。

普通成功沿用已接受抽样：每 arm×primary_category 至少1个，加其余成功10%向上取整，配对同范围、固定seed且盲化 arm。本次 critical 覆盖意味着许多输出本就全审，抽样不抵消 mandatory。Judge/AI 不代替人工，未审不算通过；每次生成前预留全失败情况下的 review capacity，不足则停派发。Bad Case 复用 review，记录首因阶段、原文/scope、缺失组、错误主张/引用、严重度/成本与单因素后续假设，不另造一套治理。

## 9. v0.2a 允许范围与真实 L1

Human Gate 接受并另行授权后的唯一切片：**Conversation → durable Turn/Run → Relevant History A+B → Working State → topic/coreference/query interpretation → 原文/保真 Rewrite/澄清 → 既有 Evidence RAG → bounded Context Assembler → validation → accepted result+state 原子 commit → Trace/PDF**。显式会话入口、最小刷新/继续/冲突/取消/重试与来源查看；Pydantic/OpenAPI 生成前端类型。PG 权威、Qdrant 可重建、Redis/Celery 原职责、LocalBlobStore 不变；会话为进程内管理，不新增 Celery 会话执行。新 durable schema 全用 Alembic，保留 v0.1 reader/Ask。

排除 Summary、vector Memory、长期个人记忆、Tool/Function Calling、MCP、Multi-Agent、检索研究/改排名、换向量库/新基础设施、独立解释调用、repair/refetch loop、自动跨重启续算、自动TTL/删除、分支/并行队列与完整纠错管理台。前述预算未知只关闭相应运行路径，不以 fake 结果宣称切片真实生成已完成。

L1 在隔离真实 PostgreSQL、受控 LocalBlobStore 与必要既有服务验证，provider 用 fake；不能用 SQLite/mock 事务证明 PG 并发。实现前授权应给固定测试场景与资源上限；实际 PG扫描/期限等绑定在候选执行前完成。以下是验收证据计划，**本轮未执行**：

| 风险 | 真实测试与必需证据 | 通过条件 / 限制 |
| --- | --- | --- |
| persistence / migration | v0.1 PG+blobs备份→Alembic升级→旧reader/新写入→进程重启→匹配备份恢复；固定数据断言与迁移revision | 原始提交/输入输出snapshot/旧引用可读；不伪造无损downgrade，无自动TTL |
| idempotency / single active | 同key同fingerprint并发提交、同key异内容、两个独立提交、admission响应丢失、显式retry重复 | 同身份同Turn/Run，异内容冲突，独立提交busy/head conflict；每Turn最多一有效结果、槽不被旧cleanup释放 |
| expected head / fence / atomicity | 两PG连接+同步屏障控制commit/cancel次序；分别注入admission后、provider后、commit前、commit后进程失效与commit回执丢失 | result/Citation/state/head/slot同事务；stale owner/head/deadline无法accepted；不确定commit先读PG，不重发 |
| recovery / effective accepted | SSE断连/刷新、后端重启、lost owner reconciliation重复、UNKNOWN | SSE只观察；durable final可恢复，未完成显示interrupted且被fence；UNKNOWN保持账本，不自动续算 |
| scope / identity | 跨Conversation/撤权/缩scope/版本变化/缺源/同文异版/旧标签注入/quote有效但不支持 | admission/read/commit均授权；immutable span/PDF解析100%；历史答案不成为当前Evidence，语义另需人工 |
| selection / state | recent-2外旧组、完整纠正链、超C/K/成员/行/字节/round-trip、pending/failed噪声、topic return、澄清后新Turn | 来源组完整或明确失败，旧假设不复活，search_incomplete可见；真实PG plan/rows examined/time与物化数分别记录 |
| overflow / accounting | 实际serializer的verified tokenizer、完整messages边界L−1/L/L+1；计量缺失/错误hash、mandatory+完整pack超界 | 无回答调用/无accepted状态；不裁pack/否定；fake容量仅证明分支；真实accounting未验证则门禁未通过 |
| compatibility / visible slice | 同scope/query/profile固定v0.1 ranking/pack/Citation→PDF对照；UI→API→Trace/PDF、刷新继续；旧取消/reader | 无确定性身份漂移，草稿不final；后端lint/format/tests、前端lint/typecheck/build，报告真实服务覆盖、失败/skips |

保留每次故障的数据库终态、身份/计数、时间界、调用账本与可恢复输入；不保存密钥/完整DB URL/原始provider错误体，不操作旧RAGFlow容器/卷。静态 M07-pre 的10 PASS 不计入此运行时通过数。L1 失败先修正确性，不能用 L3 均分抵消；一次固定矩阵完成后不反复补无关测试。

## 10. 审阅结论与交接

Product Owner 已接受单点AB0、数据构造/封存规则、描述性零新增material失败与hard全完成规则、最小E集合、未来最大预算、DEFERRED fail-closed处理及真实L1计划。**Comparison Protocol Human Gate 已完成；实现仍需单独授权；真实计量/精确执行身份/付费额度未闭合时比较仍阻断。** 不启动下一阶段、不恢复本地Calibration、不宣称已有产品赢家或发布门槛通过。接受来源及被审阅内容身份见页首；实质协议不因本次状态落实而改变。

以下两表为已接受的审阅摘要；“Frozen now”指已接受的设计/未来边界，Deferred 项保持延期，不代表执行授权。

| Decision | Frozen now | Deferred | Evidence | Trigger to revisit |
| --- | --- | --- | --- | --- |
| 数据/分母 | CAL身份；DEV6族12视图/hard7；REG6族12+V0六项；同族同split；rubric/配对分母 | 原创D/G字节hash、标签人审/封存 | H、M01/M03，Evaluation §3–5 | 连通泄漏、许可/覆盖/标签争议；候选前新版本 |
| arm身份 | V0精确commit/现有prompt；R/A/AB0设计及Oracle只诊断 | 新code/tree/prompt/model/corpus/index/accounting实际身份 | 当前Git/公开源码、ADR0009 | 身份变化使旧配对失效 |
| 首版历史 | N2/C8/K2；四分支；exact去重；纠正整组；state投影16/组成员8 | 最优值、语义泛化 | M01/M03支持结构；数值为保守默认 | 真实cutoff/selection miss，非自然长尾推断 |
| 资源/容量 | 8 round trips/64来源行/128KiB；零自动retry/refetch；完整计量/fail-closed/overflow | 扫描/期限、tokens/reserves、产品会话总额、CNY | M04/GAP、Feature §5 | 真实L1与官方身份、必要独立授权；不能看候选后设值 |
| E/序列 | E1/E8/E9/E10 active；V0→R→A→AB0→hard→REG | E2–E7；E11/E12仅trigger；Oracle0 | Evaluation矩阵、无新增VOI证据 | 已登记具体失败可改变决定才新协议 |
| 质量 | hard先行、全关键/hard通过、paired margin0、逐维Pareto、无统计泛化 | stochastic稳定性、生产频率/长尾、release结论 | 十视图构造限制、Evaluation S | 关键missing/权衡→INCONCLUSIVE，不临时扩样 |
| 预算/人审 | DEV/HARD/REG最多48/28/30 calls；48/28/36 units；所有mandatory人审 | 官方价格、token代值、支付/实施授权 | Lean内缩小上限、H不作时长预测 | 任一维到限/UNKNOWN即停；剩余不授权 |
| 实施/L1 | 一条AB0垂直路径、真实PG矩阵、v0.1保护 | 实际实现与验证结果 | Feature、ADR0006–0009、M07仅静态 | Gate接受+独立实现授权；失败不晋级 |

| Area | First-slice choice | Test/acceptance evidence | Not in scope |
| --- | --- | --- | --- |
| Conversation/Turn/Run | PG durable admission、expected head、单active、显式幂等retry | 真实并发/回执丢失/迁移/重启矩阵 | 自动队列、分支、跨重启续算 |
| History/State | AB0 A+B、完整来源/纠正、不可变snapshot与有界投影 | 超窗恢复、误混scope、组/cap/PG成本诊断 | Summary、vector/长期个人Memory |
| Interpretation | 确定skip，否则一次combined；保真Rewrite或澄清 | F类风险的新DEV标签、false skip/drift人工复核 | 分离调用、模型repair、refetch循环 |
| Evidence/Assembler | 旧structural完整pack、类型隔离、全消息计量与fail-closed | Citation→immutable span/PDF、overflow边界、真实token证据 | 检索改排、切pack、字节换算tokens |
| Commit/Recovery | result/Citation/state/head/slot原子接受，fence/UNKNOWN仲裁 | PG屏障竞态、失效进程、durable readback、唯一有效结果 | exactly-once物理模型调用声明 |
| UI/API/Trace | 显式会话、刷新继续、草稿/最终区分、Trace/PDF、生成API类型 | UI→API→PDF、旧reader/取消、lint/typecheck/build | Tool/Function Calling、MCP、Multi-Agent、新基础设施 |
