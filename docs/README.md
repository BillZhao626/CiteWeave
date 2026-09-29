# 工程文档

首次阅读请从以下页面开始：

- [快速开始](QUICKSTART.md)：离线检查、完整本地运行、公开语料摄取。
- [架构](ARCHITECTURE.md)：查询流程与数据职责。
- [语料](CORPUS.md)：来源、获取、许可与 fixture 边界。
- [数据声明](DATA_NOTICES.md)：保留的第三方摘录归属。
- [开发贡献](../CONTRIBUTING.md)：修改与验证要求。

## v0.2 规划与工程治理

以下 Blueprint / Foundation / Governance 基线、Playbook 与 v0.2 Conversational RAG Architecture 均为 **ACCEPTED — Human Review incorporated**，不代表已发布功能或实现授权。首个 Feature 与 ADR 0006–0009 原文本已获 APPROVED；Evaluation 方法论已接受，执行协议仍 **NOT EXECUTABLE**。Human Review 日期为 2026-09-28，审阅提交 `aa5755cbf70e552827f03211d2770a4dcff3626f`，记录见 [PR #3](https://github.com/BillZhao626/CiteWeave/pull/3)；实现为 NOT_STARTED。当前状态及下一阶段见 [HANDOFF](../HANDOFF.md)。

| 当前任务 | 按需阅读 |
| --- | --- |
| 产品范围、路线、里程碑与漂移检查 | [v0.2 Blueprint](V02_BLUEPRINT.md) |
| 技术取舍、责任方向、后续架构问题 | [v0.2 Foundation](V02_FOUNDATION.md)，结合当前 [Architecture](ARCHITECTURE.md) |
| 会话身份、状态生命周期、并发恢复与架构接受记录 | [Conversational RAG Architecture](V02_CONVERSATIONAL_RAG_ARCHITECTURE.md)：ACCEPTED — Human Review incorporated；[PR #2](https://github.com/BillZhao626/CiteWeave/pull/2) 为交付与审阅记录，非已实现架构 |
| 选择开发方法、AI 自主边界与人工接受 | [AI Development Playbook](AI_DEVELOPMENT_PLAYBOOK.md) |
| 提交、PR、CI、评测门槛、版本与发布审计 | [Engineering Governance](ENGINEERING_GOVERNANCE.md) |
| 首个多轮切片行为、范围、保留/恢复、Context Assembler | [First Conversational Slice Feature Spec](specs/07_V02_First_Conversational_Slice.md)：ACCEPTED — Human Feature Review incorporated |
| 数据、指标、baseline、消融、预算/候选范围冻结 | [Conversational Evaluation Spec](specs/08_V02_Conversational_Evaluation.md)：ACCEPTED — Human Evaluation Methodology Review incorporated；Calibration Plan 已接受（记录见下），Comparison Protocol Freeze 已接受，执行仍不可用 |
| 首个切片实现前所需长期决定 | [ADR 0006 状态提交](adr/0006-conversation-state-and-effective-commit.md)、[0007 Memory/Evidence](adr/0007-memory-and-documentary-evidence.md)、[0008 有界上下文](adr/0008-bounded-conversational-context.md)、[0009 profile/Trace](adr/0009-conversation-profile-and-trace.md)：均 ACCEPTED — Human ADR Review incorporated，经验参数仍 UNSELECTED |
| 已接受的 Calibration 最大资源框架 | [Cost-Aware Calibration Plan](V02_CONVERSATIONAL_CALIBRATION_PLAN.md)：ACCEPTED · 2026-09-29，[PR #4](https://github.com/BillZhao626/CiteWeave/pull/4)；Lean 选定，Recommended 未预授权，Ceiling 仅参考、未授权；LOCAL-FIRST / PROVIDER-OFF-BY-DEFAULT。该最大框架自身不授权执行；PR #5 的独立本地授权见下，provider 0 calls / 0 CNY，有限 CNY NONE/PENDING，baseline pilot 未授权 |
| 当前：recovery COMPLETE；Local Calibration 已退出 | [Bounded Local Calibration Execution Plan](V02_LOCAL_CALIBRATION_EXECUTION_PLAN.md)：ACCEPTED；原批次收据封存失败记录不变。本地状态为 LOCAL BATCH DONE / CAL PARTIAL / Comparison BLOCKED。独立授权的一次 recovery 已以字节完全相同的固定 manifest 成功持久化 M01/M03/M04/M07-pre，沿用十视图人审（10 units/5 分钟），无新增人审。详见 [HANDOFF](../HANDOFF.md)。65536 bytes 和每族 ≤16 Turns 仍仅限工作量，provider 为零 |
| 当前：Comparison Protocol 已接受 | [Comparison Protocol](V02_COMPARISON_PROTOCOL.md)：ACCEPTED — Human Comparison Protocol Review incorporated；Product Owner APPROVED，接受单点 AB0 保守默认、DEFERRED fail-closed、比较/质量规则及未来最大预算。结构性实现及 fake-provider/local L1 仍须单独授权；真实 provider/candidate execution 仍不可用 |
| 后续执行与实现 | 本地退出条件已满足，停止前置本地 Calibration，不为 PENDING 追加测量。独立 **实现前 Comparison Protocol Freeze Human Gate** 已完成，仍需实现授权；精确执行身份/计量/有限预算未闭合不比较。本轮不授权 provider pilot、候选比较或产品实现 |

本页复用为文档地图，不另建同义 index。AGENTS 只保留规则和导航；HANDOFF 只保留当前状态；Blueprint 管产品范围；Foundation 管取舍；ARCHITECTURE 管实际职责，版本架构页按标明状态记录设计及接受边界；Spec 管单功能行为；治理文档管跨切片约束；ADR 记录经各自 Human Gate 接受的长期决定，候选源于 Foundation、起草授权见 v0.2 架构；一次性 Plan 不替代长期知识。

其余 specs、ADR 与带版本前缀的文件是实现演进记录，保留当时的名称、配置和判断，不能用作最新安装入口或当前产品成绩。历史机器报告与原始实验产物不随源码发布；引用这些本地报告的历史复盘脚本不属于快速开始或公开 CI 的入口。
