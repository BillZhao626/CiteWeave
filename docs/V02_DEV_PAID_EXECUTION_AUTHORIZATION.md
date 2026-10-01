# v0.2a DEV v3 — Paid execution authorization packet

状态：**V02A_DEV_PAID_READINESS_BLOCKED** · 2026-10-01。本次仅 provider-free 准备与测试；DEV/HARD/REG 均 NOT_RUN，外部 provider/model/Judge 调用 0，支出 0 CNY。没有正值授权、付费入口或部署策略。以下已测样本不能成为真实执行预算。

## 冻结身份与核验

| 项目 | 冻结值 |
| --- | --- |
| Dataset / version | `citeweave-v02a-development-v3` / 3 |
| Dataset SHA256 | `a01953930e2893065dc6f724b6ce896015124744d6614ac14a6354f087636023` |
| Approval | `citeweave-v02a-development-v3-human-gold-20261001` |
| Approval SHA256 | `df55c120f92ee4998083872cb6bea421101fc1c9eb89c3dd730242b064debd66` |
| Checkpoint commit | `c905bb55489108aa118e669d576e037ba5c81ca1` |
| Checkpoint tree | `b6dadc84fd530bdc7fd2a22bb453b4058669d3b3` |
| Campaign proposal | `citeweave-v02a-dev-v3-paid-01-PROPOSAL`，尚非 admitted campaign |

开始时 HEAD/tree 精确匹配、工作树干净。此后只增加本次 readiness 的源文件、测试、脚本、本文与导航；未提交、push、PR、合并、tag 或 release。`load_human_gold` 重验完整 dataset、approval、全部 [12 个批准 view hashes](V02_DEV_HUMAN_GOLD_FREEZE.md)、协议及 pinned predecessor/audit hashes；v1/v2 manifests、历史 review/readiness 和 v3/approval 字节不变，七份原始 PDF/canonical 精确核验通过。未访问 sealed/REG/Holdout 或 `审计私有/`。

可复核入口：`python scripts/prepare_v02_dev_paid_readiness.py`；加 `--probe-local` 仅对本地 PG/Qdrant/model health 做只读检查。脚本首先拒绝 checkpoint 漂移及非 readiness allowlist 的改动；没有 provider factory 或 paid dispatch。完整 body、request SHA、message、reference、runtime/config/source/view hashes 存在忽略目录 `.runtime/evaluation/v02-dev-paid-readiness/provider-free-packet.json`。这些是本地测量收据，不公开机器报告。

## 付费 population 与调用上限

依据 [已接受协议 §6/§8](V02_COMPARISON_PROTOCOL.md)，本轮只包含 fixed-prefix、repeat=1 的 A/AB0；40 个前缀 Turn 是手工意图/澄清 seeds，0 模型调用，不能作为生成技术答案。HARD 的真实前驱/闭环是后续独立 stage，本轮不另跑 D4 closed-loop。

| Arm | 实际拟付费 views | 逻辑 targets | 解释条件上限 | 生成预期 / 条件上限 | 预期 / 条件 / 协议 calls |
| --- | --- | ---: | ---: | ---: | ---: |
| V0 | 无；本地 D2.V1 serializer/原单轮契约核验 | 0 | 0 | 0 / 0 | 0 / 0 / 0 |
| R | 无；D1–D6 的 V1/V2 仅本地诊断 | 0 | 0 | 0 / 0 | 0 / 0 / 0 |
| A (`cp-a-v1`) | D1.V1、D1.V2、D2.V1、D2.V2、D3.V1、D3.V2、D4.V1、D4.V2、D5.V1、D5.V2、D6.V1、D6.V2 | 12 | 7 | 10 / 11 | 17 / 18 / 24 |
| AB0 (`cp-ab0-v1`) | 同上全部 12 views | 12 | 8 | 11 / 12 | 19 / 20 / 24 |
| DEV 合计 | 两 arm × 12，含 1 个预期零调用 guard target | **24** | **15** | **21 / 23** | **36 / 38 / 48** |

协议最大解释24 + 生成24 = **48 physical calls**；冻结 skip/guard 成立时条件上限15 + 23 = **38**；Gold 预期路径15 + 21 = **36**。38 仍包含 D4.V1 的两个解释误判后生成槽；36 不包含它们。48 是接受协议的外层上限，不准把 saved slots 转给别的 case/arm/重跑。将来选择更小的38授权须先让真实 launcher 证明相同 skip/guard；目前未证明。每 logical target 只有一个 Run，显式/自动 retry、refetch、repair、Judge 均 **0**。同键恢复只读持久结果。

- A/AB0 解释：D1.V1、D1.V2、D3.V1、D4.V1、D4.V2、D5.V1、D5.V2；AB0 另含 D3.V2。
- 两臂 D2.V1/V2、D6.V1/V2 自足路径 skip interpretation，只拟 generation。
- A D3.V2 在完整纠正组检查处 `incomplete_group`，解释/生成均跳过；没有生成 allowance 转移。
- 两臂 D4.V1 预期解释后 CLARIFY，跳过 generation；D4.V2 是已冻结回复的另一 fixed-prefix target。
- 其余预期 generation；真实无 Evidence、非法解释、scope/容量/引用/期限失败会减少调用或终止，不补发。D6.V2 的 fixture 有当前 citations，所以测量包含一次生成拒答；真实空 Evidence 时现有工作流可直接拒答、无生成。

## 模型、tokenizer、价格与账户

本地配置读取仅输出安全字段：`deepseek-flash`、`answer-telecom-v1`，positive runtime policy 未配置。两阶段共用 pinned `completion_payload`：system+user 两消息、非思考、stream、include_usage；无工具/response_format/隐藏模型调用，序列化使用实际 `serialize_request`。解释共用现有 evaluation State-origin 补充文本，不修改 prompt/retrieval/ranking。

官方 recipe revision `8cadfede7063c896b944e7bae05daa3549ae97ea`；tokenizer SHA256 `81f64d1248a68ce3663e07ab3ee48b851e5df0e32d27cb98e4c9a268151e8d99`；`tokenizers==0.23.2`；accounting `deepseek-v41-text-pair-v1:<recipe revision>`。本次从 pinned 本地文件重新哈希并实际计数，包含官方 framing；不把 E5/BGE proxy 转成生成 tokens。

[官方 CNY pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) 于 **2026-10-01 04:22:53 UTC / 12:22:53 北京时间** 公开 GET，SHA256 `5a7b1832592387340f2fc456399b34b89b05f3fa167c2e35909e2fa4afe021e3`，与原接受 snapshot 字节一致。当前 `deepseek-flash` 对应公开版本 DeepSeek-V4.1-Flash；最坏适用公开单价为 cache-miss 输入 **2 CNY/M**、输出 **8 CNY/M**，匹配 repo rate identity `deepseek-flash-CNY-2026-09-13`。一律按高峰/全 cache-miss，节假日/命中折扣不降低预算。

公开 alias 不是 immutable served-weight identity。**Human gate**：明确接受此可重复性限制、确认 intended account/API endpoint 按上述 CNY rate 计费及适用附加费用、私下验证可用额度与已有月预算剩余容量；收据只记验证状态/时间，不含 credential 或 balance 数值。本次未请求账户 API，不能从公开网页证明特定账户 applicability。价格/alias/tokenizer 漂移即停止，不自动换 rate/model。

## 输入测量、输出 reserve 与费用

已保留 **36 个完整 reference request bodies**；各 body 用 reference-output 长度作 `max_tokens` 仅为合法测量样本，**没有 output reserve 的含义**。输入包含真正 serializer 发送的 system/user/schema/history/State/Evidence/framing。具体每阶段 tokens 见下表；`I/G = 输入 / reference输出`，`—` 表示预期跳过。

| View | A interpretation I/O | A generation I/O | AB0 interpretation I/O | AB0 generation I/O |
| --- | ---: | ---: | ---: | ---: |
| D1.V1 | 1819/223 | 705/18 | 1812/217 | 692/18 |
| D1.V2 | 1717/224 | 620/18 | 1829/227 | 719/18 |
| D2.V1 | — | 335/17 | — | 335/17 |
| D2.V2 | — | 335/17 | — | 335/17 |
| D3.V1 | 1728/234 | 646/16 | 1840/233 | 738/16 |
| D3.V2 | —（guard） | — | 2059/233 | 938/16 |
| D4.V1 | 2019/451 | —（澄清） | 2026/459 | —（澄清） |
| D4.V2 | 2335/112 | 388/17 | 2308/109 | 388/17 |
| D5.V1 | 1857/250 | 753/22 | 1842/240 | 728/22 |
| D5.V2 | 1851/250 | 725/19 | 1859/256 | 739/19 |
| D6.V1 | — | 421/20 | — | 421/20 |
| D6.V2 | — | 338/6 | — | 338/6 |

解释固定 specimen 输入合计 **28,901**；8 个不依赖解释的生成 specimen 输入 **2,858**；13 个依赖 fixture 解释的生成 specimen 输入 **8,779**；合计 **40,538**。reference 输出合计 **4,074**（解释3,718、答案356）；参考完整输出最大值解释 **459**、答案 **22** tokens。数值更新使用完整 Gold reference answer 和当前 citation label，未用 generator 的短 quote 代替完整 reference。

**每个 live call 的 input bound/output reserve 均 UNKNOWN；campaign input/output/total-token ceilings 均 UNKNOWN。** 不能将上表转为真实上界：PG Conversation/Acceptance/State UUID 尚未产生；真实 corpus/index/pack 未绑定；解释后 validated query/facts、选择的 history/State、检索结果均可能变化。D4.V1 误判生成的两个 conditional bodies 不存在，协议额外阶段也未有可派发身份。可固定部分的样本已精确测量，真实请求身份尚不完整。

解释 schema 仅规定最小字符串长度，facts/references/ambiguities/put 等无有限数组/字符串最大值；source-validity checks 不限制所有模型输出长度。答案上限8192字符是接受保护，不是按此小集证明的 purpose-specific reserve，非 thinking 官方最大输出384K也不是合理 campaign reserve。459/22 的参考最大值证明样本长度，不能证明合法模型输出/完整答案的必要余量；没有获接受的有限 reserve/margin rationale。本次不选择1024或任意倍数，也不改变 schema/提示词来强行取得小预算。

所需推导必须先接受两阶段 reserve `O_I/O_G` 及长度/finish failure policy，再对真实固定 framing/history/State/pack 和动态插入值给出 tokenizer/escaping 可证明的上界 `I_G(v,a,O_I)`。不能直接将 `O_I` 加到生成 input：JSON 转义、重新分词和解释引起的选择变化须覆盖。每次 dispatch 前重新序列化/计量并对已冻结 cap 与 request identity 检查；超界无 dispatch、无换 scope/丢 mandatory evidence、无临时扩大预算。

费用只允许按封闭的 per-call bounds 算 `Σ(2×I + 8×O)/1,000,000 CNY`，并纳入适用账户费用；按 Run/Turn/Conversation/arm/stage/campaign 与已有月预算同时保留最坏占用。**expected-path CNY ceiling = UNKNOWN；protocol physical-call CNY ceiling = UNKNOWN；proposed Human CNY ceiling = 未提出；当前获授权 ceiling = 0 CNY。** 不用1M/384K技术极限填空，不以reference费用或guards折扣冒充最大支出。预算测试只验证精确 Decimal 算术及 fail-closed，不提供任何授权。

## 时限、取消与 UNKNOWN

沿用协议已有安全政策，不依据未测延迟加任意余量：transport 每次25s（connect最多5s）并受剩余期限从严约束；每个外部 call 的绝对 elapsed最多 `min(35s, Run剩余)`；比较目标 Run/Turn 共用从 admission 起45s，**两阶段不各获45s/35s相加延长**，检索/接受也消耗同一剩余。45s不是产品 SLO。

本轮24个 target 的 Run elapsed 总和≤1080s；前缀40个手工 seed Run 也各受45s，故全部64个 Run 的安全算术上限2880s。每个隔离 fixed-prefix Conversation 为 `(prefix数+1)×45s`：D1.V1=135、D1.V2=180、D2.V1=45、D2.V2=90、D3.V1=180、D3.V2=225、D4.V1=90、D4.V2=135、D5各90、D6各90秒（每臂独立，非测得耗时）。prepare/setup/数据库事务等待由 campaign 外层限制，不忽略为0。

campaign 最大 elapsed **153分钟**，沿用已接受 DEV 的 setup30 + recovery15 + local60 +48个一分钟slot，跨重启不重置；串行、最大一个 active target。UNKNOWN立即停止全campaign新派发；最多15分钟recovery还未对账则 INCONCLUSIVE，保留最坏预留。取消关闭传输/停止新调用、使用持久 owner/fence/head/deadline核对，不宣称取消撤销已发账单。DISPATCHED/UNKNOWN及已完成transport但无有效结果不得换Run重发；明确确认未执行也不获本轮重试。

**执行安装仍 BLOCKED**：当前仅有 per-Run账本和 provider timeout；没有 campaign 原子预算、全局UNKNOWN暂停/绝对wall-clock watchdog、完整cancel/recovery orchestration。`bounded_stage` 是检查/传递期限，不能称同步PG操作已获硬中断。测试专用512 acceptances/1000ms history envelope不是实库付费准入；真实 PG statement/扫描计划与外层取消仍须绑定验证。设计期限不能假装已安装。

## 真实基础设施与 State-only A

仅启动并最终停回项目 `citeweave-m0-postgres-1` / `citeweave-m0-qdrant-1`；只读应用库，不迁移/seed/摄取/修改collection。旧 RAGFlow 容器与卷保持原状、停止；无 prune/reset。

| 项目 | 本次观察 / 结论 |
| --- | --- |
| 配置的应用 PG | 可连接，只读 migration **0005**；Conversation/ledger当前所需head **0011**。未升级应用库 |
| 七个原始 DEV DocumentVersion | 精确 UUID 查询 **0/7**；没有 READY/PUBLISHED、workspace/scope/index关联可核验 |
| Qdrant | HTTP200；256个现存collections，只读取inventory hash；没有DEV的PG业务绑定，不能借旧collection冒充 |
| E5 expected | `intfloat/multilingual-e5-small@614241f622f53c4eeff9890bdc4f31cfecc418b3`，384维；本地manifest/revision/path存在 |
| BGE reranker expected | `BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`；本地manifest/revision/path存在 |
| 驻留模型/真实检索 | model health连接失败；未调用embed/rerank；未证明权重文件完整/驻留或当前 immutable EvidencePack 可返回 |

**REAL_DEV_CORPUS_QDRANT = NOT_VERIFIED**。七 source/version/document/PDF/canonical identities全部保存在本地packet `sources` 并已与Gold核验；不得把 `dev-l1-*` fixture bindings写成真实index身份。真实binding缺失即停止，没有将 FixtureRepository 替换进付费执行。此前smoke的synthetic real-Qdrant测试不证明这七个新源已摄取。后续须独立准备隔离真实DEV库、合法LocalBlobStore源、真实摄取/READY commit、E5/BGE与Qdrant索引，再冻结检索/pack identity；不直接升级既有应用数据来消除本任务阻塞。

State-only A只涉及 **D1.V2/D3.V1**。现有 `execute_target/state_intent` 可验证 active State 的精确origin，在无旧raw读取/B信用下用当前Evidence生成评测artifact，并返回 `acceptance=None`；State始终non-Evidence，doc claims仅由current pack支持，physical quote validity不代表semantic support。

**paid A boundary仍 BLOCKED**：真实Run账本中synthetic DISPATCHED→COMPLETED（没有transport）后，现有 `PgBackend.fail` 的 FAILED收尾被 `provider_outcome_requires_unknown` 拒绝。新隔离PG测试两题均证明0新target Acceptance；记UNKNOWN是当前保守收尾，但一个UNKNOWN就必须暂停campaign，不能用它正常完成两题并继续。故这不是加一个简单provider注入就可安全执行的adapter。需要另行审阅 evaluation-only durable outcome/settlement方案，复用账本、保留幂等和不确定性，receipt显式 `EVALUATION_ONLY_NOT_PRODUCT_ACCEPTED`，不推进生产head/state、不fabricate Acceptance、不更改生产解释/接受语义。本次未实现这一长期边界变化。

## 输出人审与下一 Human gate

已完成12 LABEL units，不重复Gold；实际分钟NOT_MEASURED，不填0。未来 **24个 `OUTPUT:<view>:<arm>` 全部mandatory**，包括A D3.V2无调用guard的failure receipt、两臂D4.V1澄清、全部critical/hard/失败/拒答；每个输出/错误都绑定exact receipt hash、reviewer、日期、semantic支持/critical/citation/branch判定和实际分钟。HARD成员为D1.V2、D3.V1/V2、D4.V1、D5.V2、D6.V1/V2；仍在本轮DEV中全审，不另跑HARD。seed20260929盲化arm/固定排序沿用协议。未执行项记missing/NOT_RUN，不补成成功。

名义池仍 **48 units /384分钟**，12 label +24 output +最多12 dispute；输出未来部分最多36 units，**并非已获可用容量**。前次REVISE与此前复核actual units/minutes未核销，不能声称还剩36/384或重置池。未来人审可以独立记录分钟，历史未知分钟本身不必否认已完成Gold；但接受协议要求累计池和全失败review capacity预留，当前不能证明有足够容量，必须由Owner给可核销的历史消费/保守有限剩余，或显式接受处理未知历史的独立有限future-workload政策（不由assistant替Owner改协议）。不编造历史时长，不自动增加争议复核。

下一步先闭合上述技术/账户/State settlement/人审容量缺口；只补一条“允许花钱”仍不足准入。最后必须有一次显式Human正值授权，至少绑定：

- 最终campaign ID、dataset/version/SHA、approval ID/SHA、待执行code/tree/serializer/config/prompt/index identities；本checkpoint只绑定Gold，后续候选另冻结。
- 付费views/arms/repeat及最大calls（≤48；若选38须证明condition），每call/stage/Run/Turn/Conversation/arm/campaign input/output tokens和最大total；purpose-specific reserve/margin与length failure policy。
- 从这些bounds计算的有限最大CNY、rate revision/snapshot/date、provider/alias/公开model version/tokenizer/account currency applicability及alias限制接受；私下额度核验状态，不写credential/balance。
- 绝对authorization expiry、transport/call/Run/Turn/Conversation/campaign deadlines、UNKNOWN/cancel/零重试政策、真实PG/Qdrant/E5/BGE/READY/pack bindings、State-only evaluation边界、足够future review容量。

## Provider-free 验证证据

新增proposal serialization/accounting/缺失bounds拒绝/各预算维度越界/provider construction哨兵/Gold不变测试：**12 passed**。隔离真实PG的DEV行为、State-only paid settlement拒绝、aggregate预算与UNKNOWN/no-redispatch：**45 passed，0失败/skip**；仅创建/清理自己的UUID测试DB，fake retrieval/synthetic observations不证明真实DEV检索或模型质量。初始TDD因新模块尚不存在而collection failure，已修复，不计PASS。

完整 `scripts/check_release.py`：backend **433 passed /209 integration deselected**，frontend **41 passed /5 files**；Ruff lint/format **220 files**，OpenAPI/generated types、frontend lint/typecheck/build均通过。Deselected不算PASS；现有两项Python deprecation和Vite >500kB warning仍保留。所有artifact/specimen均明确非DEV、非实model output、非授权。最终allowlist/hash/whitespace和服务停回均核验；Gold保持原checkpoint，readiness改动留未提交工作树。
