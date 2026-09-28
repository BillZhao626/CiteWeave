# v0.2 Product / Roadmap Blueprint

Status: **ACCEPTED — Human Review incorporated** · 2026-09-27

本页描述已接受的产品方向，不代表已发布能力，也不授权实现。Product Owner 对 [PR #1](https://github.com/BillZhao626/CiteWeave/pull/1) 提案提交 `c3da2e4` 作出 APPROVED WITH REQUIRED CHANGES，本页已落实该决议；接受范围不包括未来 Architecture、Feature Specs、Evaluation Spec 或 ADR。当前公开基线为 `main` / `v0.1.0`，实际能力与限制仍以 [README](../README.md) 和[当前架构](ARCHITECTURE.md)为准。技术取舍见 [Foundation](V02_FOUNDATION.md)，交付门禁见[工程治理](ENGINEERING_GOVERNANCE.md)。

## 北极星与用户问题

CiteWeave 是面向技术文档的证据问答工作台：用户连续讨论一个问题时，系统应理解当前意图，并让最终回答的引用仍可沿 Answer → Citation → Evidence → 固定版本 PDF 核对。连续对话的流畅度不能以来源、检索范围或事实支持为代价。v0.2 继续面向个人、本地、单维护者项目，不升级为企业服务承诺。

典型体验：先询问某协议约束，再追问“它在另一种情况下呢”；插入一个无关问题后返回先前任务；会话变长后仍能找回相关限制；刷新后继续会话并检查某轮究竟使用了哪些历史与文档证据。

## v0.2 范围

- Session-scoped 会话及持久状态：Recent Turns、Working Memory、Conversation State、Summary、Relevant Memory Selection / Retrieval。内存不是每轮拼接完整聊天记录。
- 当前问题结合相关状态，识别话题变化、消解指代、必要时改写为独立检索问题；保留原问题，歧义无法可靠消除时澄清，不能猜测实体或悄悄改变否定、条件、文档版本和用户范围。
- 复用现有知识检索 / 精排与有界 EvidencePack；选择相关历史后组织上下文，生成并验证最终回答，再更新会话状态。失败、取消和未验证草稿不能变成已确认事实。
- **Relevance first, Recency second**：语义、实体和任务相关性优先，近期性只能在相关性相近时辅助选择。必须用“旧而相关 / 新而无关”的对照案例验证，不能以时间衰减直接覆盖相关性。
- 有界 token / 上下文与摘要更新；可检查原问题、改写、选中历史、状态版本与文档证据的关系。正常 UI 保留简洁会话与引用操作，诊断细节进入 Runs / Trace。
- 显式多轮行为评测和既有单轮证据路径回归。

Topic Shift 是一等产品行为：Conversation State 不能无限继承旧话题或实体假设，旧上下文不得污染实质不同的新问题。状态重置、部分重置、实体替换、约束失效及按新话题限定记忆选择均是可能机制，具体方案留给 Architecture Design。

上述是能力与数据依赖，不是冻结的串行流水线。Topic Shift、Coreference、Rewrite 可以组合、跳过或用确定性逻辑完成；是否需要模型调用必须由评测、错误代价和预算支持。相关记忆可参与消解和改写，不能机械地只放在知识检索之后；准确阶段次序留给 Architecture Design。

会话内容只提供意图、约束与历史线索。过去的模型回答与摘要不成为新的知识来源；延续事实主张需要重新检查授权、当前查询范围及原始证据身份。历史引用可以回看，但不能自动授权在新范围中使用。

## 非目标与 v0.3 边界

v0.2 不要求跨会话长期用户记忆、用户画像、自动个人化、多租户 RBAC、任意 Agent 框架、工具执行、OCR、通用 PDF 正确性、新基础设施或吞吐量提升。没有证据时不替换现有检索技术，也不重解释历史 Run、冻结数据或 v0.1 指标。

v0.3 的候选方向是 Tool / Function Calling Runtime，可能提供 search_documents、inspect_evidence、open_pdf_page、inspect_document_structure、inspect_run_trace。届时单独审阅 schema 校验、权限、超时、重试 / fallback、幂等、tracing 和工具结果处理；本轮不定义工具协议、调度器、执行循环或接口，也不为它提前建设抽象层。

## 路线与 Done

| 阶段 | 目标与退出证据 | 人工门禁 |
| --- | --- | --- |
| 本轮 Blueprint + Foundation + Governance | 人工决议已落实、文档提交推送、最新 PR CI 通过，供 owner 最终合并审阅 | 基线已接受；本轮不合并或开始架构设计 |
| v0.2 Architecture Design | 责任、状态生命周期、失败边界、迁移影响与备选方案；列出所需 ADR | 重要责任边界与长期决策获明确接受 |
| Feature Spec / Eval protocol | 每个切片的用户行为、异常行为、非目标、测试、数据与预算预注册 | 行为和发布门槛在实现、调参前接受 |
| Vertical Slice | 一个可运行的端到端用户结果，同时包含持久化、API、UI、Trace 与验收；逐步增加复杂度 | 普通实现按已接受范围自主推进，范围变化回门禁 |
| v0.2 alpha | 至少一条完整多轮证据路径可复现，已完成范围满足 alpha 门禁，明确剩余能力 | 允许外部试用的人工决定 |
| v0.2 RC → stable | 全范围、冻结评测、单轮回归、升级恢复、文档、干净安装通过 | 精确发布提交的人工 release acceptance |
| v0.3 | 证据工具运行时的独立产品周期，先论证用户任务收益 | 不从 v0.2 接受自动推导授权 |
| 后续 0.x（版本号待定） | 依据实际使用补可靠性、数据生命周期、兼容性、可部署性与评测覆盖 | 每轮重新选择产品问题，不预设全部平台能力 |
| v1.0 | 声明公共 API / 行为兼容面、支持环境、迁移 / 弃用政策；在这些边界上有重复验收与可维护证据 | 质量与兼容承诺获接受；不是日历期限或功能数量门槛 |

## 每个实现里程碑前的 drift check

在对应 PR / Spec 记录：引用本 Blueprint 的接受版本与决定链接；该切片服务的用户问题；新增 / 排除范围；是否保留来源身份、检索范围与 Relevance-first；成本、隐私或基础设施是否改变；验收是否仍与冻结 protocol 一致。无变化记一段结论即可；有变化先更新提案并走相应 Human Gate，不把实现事实当作范围批准。

## 已落实的 Human Review 决议

1. 接受 session-scoped Conversational RAG 和上述非目标；接受对流水线顺序与“每个能力独立调用模型”的挑战。
2. 接受 Foundation 的责任方向，但详细 schema / API / 生命周期留待架构审阅。
3. 接受工程治理的测试范围、Git 生命周期与人工接受记录；冻结评测维度、失败分类和硬不变量。最终概率性质量门槛由后续 Evaluation Spec 在数据、指标与 baseline 方法明确后论证，并在使用评测结果进行实现决策 / 调参前冻结。
4. 接受 main 保护方向，实际配置另行决定。本 PR 不改变远端设置。

三项最大风险：摘要和历史回答污染事实依据；相关性选择与改写漂移而丢失用户限制；多轮状态在取消、并发、重试和刷新中出现不一致且难以重放。对应的发布否决项与验证安排见[工程治理](ENGINEERING_GOVERNANCE.md)。
