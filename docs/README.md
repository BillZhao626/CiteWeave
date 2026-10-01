# 工程文档

首次阅读请从以下页面开始：

- [快速开始](QUICKSTART.md)：离线检查、完整本地运行、公开语料摄取。
- [架构](ARCHITECTURE.md)：查询流程与数据职责。
- [语料](CORPUS.md)：来源、获取、许可与 fixture 边界。
- [数据声明](DATA_NOTICES.md)：保留的第三方摘录归属。
- [开发贡献](../CONTRIBUTING.md)：修改与验证要求。

## v0.2 规划与工程治理

以下 Blueprint / Foundation / Governance 基线、Playbook 与 v0.2 Conversational RAG Architecture 均为 **ACCEPTED — Human Review incorporated**，不代表已发布功能或实现授权。首个 Feature 与 ADR 0006–0009 原文本已获 APPROVED；Evaluation 方法论已接受，执行协议仍 **NOT EXECUTABLE**。Human Review 日期为 2026-09-28，审阅提交 `aa5755cbf70e552827f03211d2770a4dcff3626f`，记录见 [PR #3](https://github.com/BillZhao626/CiteWeave/pull/3)。Implementation #1 已进入 accepted main 基线 `3b10229`；Implementation #2 已进入 accepted main `2a0c406`；Implementation #3 已进入 accepted main `bebdb72`；Implementation #4 已进入 accepted main `0b45237`；Implementation #5a 已进入 accepted main 基线 `43d057b`（PR #12）；另行授权的 Implementation #5b 已在现有 Ask 中实现 React 会话、同键恢复、Citation/PDF 与 Trace Inspector，前端/离线/真实隔离 PG API 及 deterministic Chromium E2E 通过，等待 Human Implementation Review；生产 runtime 未开放，v0.2a 未完成。当前状态及下一阶段见 [HANDOFF](../HANDOFF.md)。

| 当前任务 | 按需阅读 |
| --- | --- |
| 当前：Paid DEV readiness BLOCKED；provider-free only | [单一授权包](V02_DEV_PAID_EXECUTION_AUTHORIZATION.md)：Gold/checkpoint不变；A/AB0各12目标，预期36/条件38/协议48 calls；live tokens/CNY仍UNKNOWN。应用PG0005、DEV versions0/7、真实index未绑定；State-only A付费收尾/campaign保护/人审累计容量未闭合。provider/Judge/spend0、DEV/HARD/REG NOT_RUN，无付费授权 |
| 冻结数据：DEV v3 Human Gold APPROVED / FROZEN | [冻结记录与12个view哈希](V02_DEV_HUMAN_GOLD_FREEZE.md)、[批准的人审表](V02_DEV_DATA_REVIEW.md)、[readiness](V02_DEV_READINESS.md)：外部不可变 attestation 绑定原 v3 字节；12 LABEL 单位，分钟未测量；DEV/HARD/REG及provider/Judge仍0，付费执行未授权。v1/v2历史保留，真实DEV结果不得修改v3 |
| 历史：DEV v3；TEST_FIRST_READY_FOR_HUMAN_FREEZE | [完整人审表](V02_DEV_DATA_REVIEW.md)、[针对性重审](V02_DEV_TEST_FIRST_AUDIT_V3.md)、[交付](V02_DEV_READINESS.md)：Owner 明确 D1.V2 return 与 pending/active State 为不同维度；其他11题不变。v2 字节及历史保留；人审未签，DEV/provider/Judge=0，无付费授权工作 |
| 历史：DEV revision 2；HUMAN_DATA_REVIEW_REQUIRED | [HANDOFF](../HANDOFF.md)、[v2 交付与付费门禁](V02_DEV_READINESS.md)、[完整 12-view 人审表](V02_DEV_DATA_REVIEW.md)、[v1 人审历史](V02_DEV_DATA_REVIEW_V1.md)、[Owner 澄清记录](V02_DEV_READINESS_BLOCKER.md)：首次人审 REVISE；D1.V2/D3.V1 A 可用当前 State 解析意图（评测输出，无旧原文/B 分/生产 Acceptance）；D3.V2 保持完整纠正组，D4.V2 覆盖分母 N/A。付费门禁仍未解决，Provider=0，DEV/HARD/REG NOT_RUN，#5d NOT_STARTED |
| 当前：Implementation #5b React 会话 / Browser E2E 人审 | [实际 Architecture / UI / API](ARCHITECTURE.md)、[HANDOFF](../HANDOFF.md)：复用 Ask/文档/PDF，显式版本 scope、持久 head/Run/三类结果、同键恢复及安全 Trace；有限 SSE 不作为实时流，使用有界 GET 读回；deterministic 服务端测试 runtime 仅用于隔离 E2E。默认生产 runtime 不可用，history query 仍 fail-closed，无 schema/迁移变化；物理引用验证不证明语义支持 |
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
| 后续执行与实现 | Implementation #5b 的独立授权覆盖现有 API 上的 React 会话与 deterministic browser E2E/验证/PR；#5c 未开始，完整 Trace 重建与执行计量、生产 runtime 等后续增量须另行授权。停止前置本地 Calibration，不为 PENDING 追加测量。精确执行身份/计量/有限预算未闭合不比较，不授权 provider pilot 或候选比较 |

本页复用为文档地图，不另建同义 index。AGENTS 只保留规则和导航；HANDOFF 只保留当前状态；Blueprint 管产品范围；Foundation 管取舍；ARCHITECTURE 管实际职责，版本架构页按标明状态记录设计及接受边界；Spec 管单功能行为；治理文档管跨切片约束；ADR 记录经各自 Human Gate 接受的长期决定，候选源于 Foundation、起草授权见 v0.2 架构；一次性 Plan 不替代长期知识。

其余 specs、ADR 与带版本前缀的文件是实现演进记录，保留当时的名称、配置和判断，不能用作最新安装入口或当前产品成绩。历史机器报告与原始实验产物不随源码发布；引用这些本地报告的历史复盘脚本不属于快速开始或公开 CI 的入口。
