# v0.2a DEV v3 — Paid execution authorization packet

修订说明（2026-10-01）：本页候选/环境收据属于历史提交 `4cd7390`；该版0012未接受。
另行授权的 provider-free schema 修订及新候选见 [0012修订人审包](V02_0012_REVISION_REVIEW.md)。
历史 DEV 库/收据未覆盖或升级，不构成修订版 schema 证明；旧候选身份不能授权新代码。
schema/ADR 仍 PENDING，金额/provider 授权仍0；此页不是修订候选的执行安装许可。

状态：**V02A_DEV_PAID_REMEDIATION_BLOCKED** · 2026-10-01。仅 provider-free implementation/verification；当前真实授权 **0 calls / 0 tokens / 0 CNY**。DEV/HARD/REG NOT_RUN；external LLM/Judge/account API=0，支出0。技术实装/本地验证完成，但用户指定的accepted head0011不能默认为接受新head0012。评测专用持久policy需要的additive migration0012尚待Human接受；本候选可供实现审阅，当前不具备付费执行资格。金额/账户确认不能越过该额外门禁。

## 保留 BLOCKED 证据与冻结身份

先核验原readiness diff与Gold，完成原检查，再创建本地 BLOCKED checkpoint：commit 5c80f0f74a3f2c96aced57700cdab93123d586a6 / tree 9ae13d6801cd958d35fa62aadc78c3b00f719ec4。原授权文档SHA256 1e796521f524e24b7d0382dc7610b99b0796f5d4f28eeb90e0ebdf8678e23503；原 measurements/报告/原文件字节封存忽略目录 blocked-5c80f0f/，原文内容还保留在本文末尾。无 push/PR/merge/tag。

Gold checkpoint c905bb55489108aa118e669d576e037ba5c81ca1 / tree b6dadc84fd530bdc7fd2a22bb453b4058669d3b3。dataset citeweave-v02a-development-v3 SHA256 a01953930e2893065dc6f724b6ce896015124744d6614ac14a6354f087636023；approval citeweave-v02a-development-v3-human-gold-20261001 SHA256 df55c120f92ee4998083872cb6bea421101fc1c9eb89c3dd730242b064debd66。12 views、pinned v1/v2 history、7 PDF/text hashes重验；原字节不改，未读审计私有/或sealed。

完整本地包：本文与 .runtime/evaluation/v02-dev-paid-remediation/{environment.json,contracts-head0012.json,candidate.json}。提交后 scripts/freeze_v02_dev_candidate.py 对最终干净HEAD/tree、真实环境和所有identities再核验，写入不可变candidate.json并在隔离PG创建DISABLED/零grant。完整候选commit/tree在该收据和最终交付中明确列出，避免在提交自身写循环自哈希。未来Human policy必须逐项绑定这些身份；任何tracked diff/新HEAD/环境漂移均拒绝执行。历史prepare_v02_dev_paid_readiness.py仍绑定旧checkpoint，不能用于当前候选。

## A：有限请求与费用

O_I=1561 tokens：冻结参考解释完整JSON包含全部defaults，indent=2后最大UTF8字节1561；按singleton byte最差分词构造明确有限安全余量，原参考最大459 tokens。财务reserve不承诺任意合法模型输出都能完成；生产DTO不加max_length、解释语义不变。

O_G=32768 tokens：覆盖现有完整答案8192 Unicode codepoints guard，含引用label，每字符至多4 UTF8 bytes，普通ByteLevel tokens≤bytes。参考最大22 tokens仅作观察，不当预算；不复用旧1024，不缩短产品语义。

每次请求显式max_tokens。截断/非stop/不完整DONE/invalid JSON/schema/特殊token字面量/超reserve或既有答案guard均fail closed，无retry/repair。完整已知但结构无效的输出保留COMPLETED计量并关闭FAILED目标；不完整传输/网络不确定性保持UNKNOWN并停止campaign。

动态输入采用保守**符号上界**，不是40538 specimen总量、不是分段token计数相加。对完整generation serializer：固定PG history/state全部可注入项按UTF8 bytes计，最长mode/topic；I输出每普通token最多128 decoded UTF8 bytes；合法fact补默认字段/UUID规范化至多2倍原JSON字节（最短current fact51 bytes，nullable defaults最多35 bytes，UUID规范化增量仍在2倍内）；query既有512 codepoints guard×6 JSON escaping bytes；7份固定ASCII corpus当前pack≤6400 chars/bytes；完整message字节上界+5官方framing tokens。固定ByteLevel/BPE无normalizer/额外prefix，merge只合并初始bytes，因此完整序列token数不超过该整数界。它不声称紧致最优或穷举所有输出；每个实际body在PREPARED及before_send再完整serialize、用官方tokenizer精确recount，超槽cap在DISPATCHED前拒绝。

Tokenizer SHA256 81f64d1248a68ce3663e07ab3ee48b851e5df0e32d27cb98e4c9a268151e8d99；recipe 8cadfede7063c896b944e7bae05daa3549ae97ea；tokenizers0.23.2；text-pair/non-thinking/无工具。HTTP JSON转义不作为模型content额外token重复计费。以下是该固定协议的保守财务上界，不是实账保证或质量结论。

| 项目 | 条件最大值 |
| --- | ---: |
| I stage input | 2328 |
| G stage input | 411919 |
| Campaign input | 6196897 |
| Campaign output | 777079 |
| Campaign total | 6973976 |
| Campaign CNY | 18.610426 |

每槽cap（I output1561 / G output32768；缺席/未用槽不可转让）：

| View / arm | I input | G input | Calls max | CNY max |
| --- | ---: | ---: | ---: | ---: |
| D1.V1:cp-a-v1 | 1811 | 410775 | 2 | 1.099804 |
| D1.V1:cp-ab0-v1 | 1825 | 410775 | 2 | 1.099832 |
| D1.V2:cp-a-v1 | 1712 | 410538 | 2 | 1.099132 |
| D1.V2:cp-ab0-v1 | 1834 | 410775 | 2 | 1.099850 |
| D2.V1:cp-a-v1 | 0 | 348 | 1 | 0.26284 |
| D2.V1:cp-ab0-v1 | 0 | 348 | 1 | 0.26284 |
| D2.V2:cp-a-v1 | 0 | 348 | 1 | 0.26284 |
| D2.V2:cp-ab0-v1 | 0 | 348 | 1 | 0.26284 |
| D3.V1:cp-a-v1 | 1727 | 410566 | 2 | 1.099218 |
| D3.V1:cp-ab0-v1 | 1837 | 410823 | 2 | 1.099952 |
| D3.V2:cp-a-v1 | 0 | 0 | 0 | 0 |
| D3.V2:cp-ab0-v1 | 2055 | 411291 | 2 | 1.101324 |
| D4.V1:cp-a-v1 | 2042 | 411229 | 2 | 1.101174 |
| D4.V1:cp-ab0-v1 | 2021 | 411229 | 2 | 1.101132 |
| D4.V2:cp-a-v1 | 2328 | 411919 | 2 | 1.103126 |
| D4.V2:cp-ab0-v1 | 2326 | 411919 | 2 | 1.103122 |
| D5.V1:cp-a-v1 | 1846 | 410787 | 2 | 1.099898 |
| D5.V1:cp-ab0-v1 | 1836 | 410787 | 2 | 1.099878 |
| D5.V2:cp-a-v1 | 1858 | 410791 | 2 | 1.099930 |
| D5.V2:cp-ab0-v1 | 1860 | 410791 | 2 | 1.099934 |
| D6.V1:cp-a-v1 | 0 | 446 | 1 | 0.263036 |
| D6.V1:cp-ab0-v1 | 0 | 446 | 1 | 0.263036 |
| D6.V2:cp-a-v1 | 0 | 350 | 1 | 0.262844 |
| D6.V2:cp-ab0-v1 | 0 | 350 | 1 | 0.262844 |

| Arm | Calls max | Input | Output | Total | CNY max |
| --- | ---: | ---: | ---: | ---: | ---: |
| cp-a-v1 | 18 | 2891421 | 371375 | 3262796 | 8.753842 |
| cp-ab0-v1 | 20 | 3305476 | 405704 | 3711180 | 9.856584 |

最坏cache-miss input2/output8 CNY/M；RATE_CARD=deepseek-flash-CNY-2026-09-13。Decimal (input×2+output×8)/1e6，不依赖cache hit/夜间折扣。既有2026-10-01T04:22:53Z官方公开价格快照SHA256 5a7b1832592387340f2fc456399b34b89b05f3fa167c2e35909e2fa4afe021e3 保留，Human在授权时须确认快照仍适用于私人CNY账户；无account API或余额读取。36预期路径财务上界 16.441222 CNY，仅作说明，不是实际消费预测。

## B：真实隔离 corpus/runtime

专用PG DB cw_dev_v3_a01953930e289306：在accepted0011完成真实摄取，仅为本evaluation seam加0012。原配置应用DB仍0005、未升级/seed；只有7个固定Document/Version、专用LocalBlobStore。真实production ingestion、source/text/canonical_block hashes、READY durable commit/PUBLISHED index、local E5/BGE、production retrieval及物理引用7/7核验。没有broker worker、新基础设施或RAGFlow改动。

E5 intfloat/multilingual-e5-small@614241f622f53c4eeff9890bdc4f31cfecc418b3，384维、dense_only、normalize、原query/passage prefixes；BGE BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e。完整environment的规范SHA256 77a696e9cd7a29c169a4e0ea13fc3dfe60a8ee1881fee2c01f10bc2df6052749，包括7 bindings/7 retrieval packs/citations。首轮Qdrant UnexpectedResponse导致7个本地ingestion失败，保留FAILED_FINAL receipts/BUILDING索引；一次明确local recovery-01使用新生产namespace，成功READY/PUBLISHED。没有provider重试、无删除历史证据。

| Source | Version | Artifact | Qdrant collection | Profile SHA256 |
| --- | --- | --- | --- | --- |
| D1.manual | 8077f914-b388-5a27-afdb-699735635d6b | e5056658-7bb5-5045-9736-5fbf2d8704e8 | cw3_v8077f914b3885a27afdb699735635d6b_jfb25ab0d08c850538a6af3fc7801e01c_f1 | f160a4839133f5726e9eba1f96f7bf35ae31cb99ef98dee89bcdd22ddb38f4df |
| D2.manual | 96589c61-798e-574c-9fba-c04d17bdfc8a | 2a158931-9523-5aa5-a60b-1f619f7ffadf | cw3_v96589c61798e574c9fbac04d17bdfc8a_jf62ed1e7d641557ba39521a4d1425373_f1 | f160a4839133f5726e9eba1f96f7bf35ae31cb99ef98dee89bcdd22ddb38f4df |
| D3.manual | 39c513f3-4a62-5236-8efd-d15dab4e1787 | bd6d66d0-4eeb-5f5e-a457-94620fbbbab3 | cw3_v39c513f34a6252368efdd15dab4e1787_jbfbeda5b55b25379a5f2a60227654949_f1 | f160a4839133f5726e9eba1f96f7bf35ae31cb99ef98dee89bcdd22ddb38f4df |
| D4.manual | 1506a478-7da5-51d3-8e26-f71599e4550f | a7e87cda-ed0f-5e9f-9edc-3c5cab83debf | cw3_v1506a4787da551d38e26f71599e4550f_jc962ebe264505280b7e78a5da0f2cf56_f1 | f160a4839133f5726e9eba1f96f7bf35ae31cb99ef98dee89bcdd22ddb38f4df |
| D5.manual | 1cf8706f-2078-579a-907c-84e6e6b5fc6d | aa560ae0-5877-515f-b9a5-02705fa606c0 | cw3_v1cf8706f2078579a907c84e6e6b5fc6d_j1e26ab39a4ca59938d4b73d4270a02cf_f1 | f160a4839133f5726e9eba1f96f7bf35ae31cb99ef98dee89bcdd22ddb38f4df |
| D6.ledger | f1d40561-6c03-5d72-80f3-05413942d7d0 | 94ed8728-af80-5c7f-bd82-a171ffe1d108 | cw3_vf1d405616c035d7280f305413942d7d0_je916ec2d9ae151628cc28ebbf54ef0a3_f1 | f160a4839133f5726e9eba1f96f7bf35ae31cb99ef98dee89bcdd22ddb38f4df |
| D6.contingency | 84f2de55-f6f4-5ddf-9e4c-658752ef3091 | c72a7552-9f8e-5891-8fdd-98cdc9164db1 | cw3_v84f2de55f6f45ddf9e4c658752ef3091_j26f0f9942ee45fe797218ab2d6953d91_f1 | f160a4839133f5726e9eba1f96f7bf35ae31cb99ef98dee89bcdd22ddb38f4df |

全部PDF/text/canonical_block/tree/membership/BM25 hashes在本地不可变contracts。dev_launcher只构造RealDevBackend、StructuralEvidenceRetriever(ModelGateway())，没有FixtureRepository/provider_factory参数；完整预检real PG/Qdrant/citations，每次before_send重验Git/Gold/PDF/config/prompts/protocol/tokenizer/rate/models/PG bindings，production retriever自身验证当前index。物理引用正确不等于语义支持，无真实DEV答案/质量赢家。

## C/D：收尾、硬slot和campaign guard

[ADR0012](adr/0012-dev-campaign-settlement.md)记录责任与迁移。State-only A D1.V2/D3.V1无target产品Run/Acceptance/head/state写入；既有cw2_eval_cases关账，明确EVALUATION_ONLY_NOT_PRODUCT_ACCEPTED。cw4_provider_phases仍唯一call ledger，PREPARED→DISPATCHED→COMPLETED/UNKNOWN，复用原Decimal accounting。完整已知output/hash/usage同事务记录，已知目标在取消/过期后仍能关账，保持STOPPED、不把COMPLETED改UNKNOWN；同键只读durable receipt。UNKNOWN持久OUTCOME_UNKNOWN+STOPPED/INCONCLUSIVE，保留reservation/部分usage；普通目标仍用原product Acceptance guard。

cw6_dev_campaigns绑定campaign UUID、Gold/approval、code/tree/config/prompts/provider/tokenizer/rate/index/protocol、24固定case/repeat1、固定38 phase slots、calls/input/output/total/CNY、授权到期/绝对deadline。PG row lock单active target，prepare/dispatch合计全部永久reservation；1s lock/statement timeout、flush后重验PG clock。real transport必须durable HUMAN/ACTIVE/positive finite grant，调用者对象/SYNTHETIC零授权marker不能给HTTP授权。DISABLED不可升ACTIVE；不自动扩大预算。

执行absolute deadline≤153 minutes，创建真实grant时必须填明确UTC；授权到期≤此deadline。每target45s，每call≤min(35s,target remaining)，原HTTP25s/connect5s。取消由dev_campaign.cancel持久化，禁止新dispatch，保留已DISPATCHED费用/观测。进程丢失无自动resume；受守卫入口将expired DISPATCHED保守UNKNOWN并停止。24结果完成关闭spending，再进行独立Human review；不存在后台自动付费执行。

**38 executable max**：15 I+23 G。D2.V1/V2、D6.V1/V2两arm固定无I；D3.V2 A固定零slots且real PG证明incomplete_group；D4.V1两arm条件G仍保留。DevPolicy拒绝新增缺席槽；每(case,purpose)只能一次，attempt1，取消/skip不能转让。expected36（15I+21G）仅Gold路径说明；protocol48为历史外层上限，本次不能消费额外10槽。V0/R/retry/refetch/repair/Judge=0；每paid目标仅一次history读取，不新跑HARD闭环。

## 尚未关闭的 accepted-head 门禁

用户Blocker B要求accepted Alembic head0011。真实七源摄取/检索已在0011完成；为数据库强制不可变campaign policy及其账本防护，本次在专用环境进一步添加0012，未改应用库。已有0011→0012与legacy reader/生产guard兼容验证，但兼容测试不等于0012接受。所需明确决定：接受这个评测专用additive schema/ADR，或要求另行调整为严格0011。当前schema_acceptance_id/schema_accepted_at均null；HUMAN policy验证也必须具有单独schema acceptance identity/timestamp，否则real dispatch仍拒绝。未自行作Accepted决定。

因此不能宣称仅剩paid/account确认，也不能将本候选标READY_FOR_PAID_AUTHORIZATION。其余A输出储备/保守动态token界、真实7源、State-only关账、38槽及五维campaign guard已实现并provider-free验证；head接受门禁是明确剩余项。

## 后续 Human fields

未来仅此campaign **24 mandatory OUTPUT+up to12 DISPUTE=36 units /288 minutes**，单独finite future-work pool。人工开始前核对剩余units/minutes，使用剩余分钟停止计时，不在耗尽后开启新review；receipt记prospective actual minutes、reviewer、decision、hash和PG timestamp；超额/重复unit拒绝，24 OUTPUT齐备才标reviewed，不自动promotion/winner。Gold历史12 LABEL分钟仍NOT_MEASURED，不推定历史累计分钟满足旧上限，也不重写Gold accounting。

当前下列checks全PENDING/false，confirmation timestamp=null，authorization_id=null：

- intended DeepSeek account/endpoint https://api.deepseek.com/chat/completions；
- billing currency CNY与当前rate快照适用；
- 接受public deepseek-flash / DeepSeek-V4.1-Flash alias无法固定immutable weights的复现限制；
- 当前worst-case input2/output8 CNY/M快照仍有效；
- private balance和remaining monthly budget足够有限grant，只记录bool/status+timestamp，不保存余额/credentials，不调用账户API；
- 单独Human有限calls/input/output/total/CNY授权、新campaign UUID、exact候选commit/tree/all identities、24case/38slots、明确UTC expiry/153min deadline和288min未来review工作池；
- accepted0012 schema/本implementation/ADR的人审结论与schema_acceptance_id/schema_accepted_at。数据、代码、环境、价格、账户漂移均不能重用授权。

candidate.json仅DISABLED/零grant提案，不可变。未来必须另给明确Human positive policy；READY标签、mode编辑、env key、测试marker、时间经过均不构成批准。

## 验证与实际限制

最终provider-free release：backend443 passed /228 integration deselected，frontend41 passed/5 files，232 Python files lint/format、生成OpenAPI/TS、typecheck、frontend lint/build通过。重点PG+DEV/migration/provider suite64 passed，最新Core/campaign suite62 passed（与64/443有重叠，不合计），均0 failures/skips。原checkpoint检查backend433/frontend41及历史BLOCKED证据保留。

失败历史如实保留：Docker daemon最初未运行，启动Desktop的自动审批拒绝后由Owner手动启动；首次real ingestion失败后一次显式local recovery成功；一个测试SQL绑定写法和fake Accounting缺属性修正；首次全release有18个PG setup errors，因为新文件未标integration，修正后443/228完整通过。上述失败不记PASS。保留2个Python deprecation和Vite chunk>500kB/plugin timing warnings，不改无关代码。

Gold admission/12-view hashes/7 source与canonical hashes、专用数据库head0012/真实7 READY-PUBLISHED bindings、7次local E5/BGE/Qdrant检索与物理引用通过。离线完整body/escaping/最大pack计数、truncation/schema fail-closed、五维预算/Decimal、State-only两题零Acceptance/head、同键恢复、UNKNOWN/no-redispatch、取消保留计费、deadline、并发fence、immutable policy及零授权provider-construction/real-dispatch sentinel通过。call bridge采用零real grant的SYNTHETIC marker和fake transport，仅在测试中显式绕开入口并关闭real_transport标志；真实入口和PG real_transport gate分别证明拒绝这些模式，不创建正值Human授权。

不调用外部LLM、不读取账户、无付费输出。Synthetic marker/transport tests均real grant=0，仅机制证据；real local E5/BGE/PG/Qdrant并不证明答案语义质量或实际provider bill。production默认runtime/history admission不开放，#5d NOT_STARTED。独立DB/blob/index保留供未来同一候选复核；仅停止本次使用的项目服务/自建gateway，旧停止RAGFlow容器/卷不动。

---

# Preserved BLOCKED readiness at 5c80f0f (historical; conclusions above supersede only with new evidence)

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
