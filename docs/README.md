# 工程文档

首次阅读请从以下页面开始：

- [快速开始](QUICKSTART.md)：离线检查、完整本地运行、公开语料摄取。
- [架构](ARCHITECTURE.md)：查询流程与数据职责。
- [语料](CORPUS.md)：来源、获取、许可与 fixture 边界。
- [数据声明](DATA_NOTICES.md)：保留的第三方摘录归属。
- [开发贡献](../CONTRIBUTING.md)：修改与验证要求。

## v0.2 规划与工程治理

以下 Blueprint / Foundation / Governance 基线、Playbook 与 v0.2 Conversational RAG Architecture 均为 **ACCEPTED — Human Review incorporated**，不代表已发布功能或实现授权。Feature Specs、Evaluation Spec 和未来 ADR 文本尚未接受；四个 ADR 领域已获下一规划阶段起草授权；实现为 NOT_STARTED。当前状态及下一阶段见 [HANDOFF](../HANDOFF.md)。

| 当前任务 | 按需阅读 |
| --- | --- |
| 产品范围、路线、里程碑与漂移检查 | [v0.2 Blueprint](V02_BLUEPRINT.md) |
| 技术取舍、责任方向、后续架构问题 | [v0.2 Foundation](V02_FOUNDATION.md)，结合当前 [Architecture](ARCHITECTURE.md) |
| 会话身份、状态生命周期、并发恢复与架构接受记录 | [Conversational RAG Architecture](V02_CONVERSATIONAL_RAG_ARCHITECTURE.md)：ACCEPTED — Human Review incorporated；[PR #2](https://github.com/BillZhao626/CiteWeave/pull/2) 为交付与审阅记录，非已实现架构 |
| 选择开发方法、AI 自主边界与人工接受 | [AI Development Playbook](AI_DEVELOPMENT_PLAYBOOK.md) |
| 提交、PR、CI、评测门槛、版本与发布审计 | [Engineering Governance](ENGINEERING_GOVERNANCE.md) |
| 单个功能实现 | 后续已接受的 Feature Spec + 相关 ADR；本轮尚无 Conversational RAG Feature Spec |

本页复用为文档地图，不另建同义 index。AGENTS 只保留规则和导航；HANDOFF 只保留当前状态；Blueprint 管产品范围；Foundation 管取舍；ARCHITECTURE 管实际职责，版本架构页按标明状态记录设计及接受边界；Spec 管单功能行为；治理文档管跨切片约束；ADR 记录经各自 Human Gate 接受的长期决定，候选源于 Foundation、起草授权见 v0.2 架构；一次性 Plan 不替代长期知识。

其余 specs、ADR 与带版本前缀的文件是实现演进记录，保留当时的名称、配置和判断，不能用作最新安装入口或当前产品成绩。历史机器报告与原始实验产物不随源码发布；引用这些本地报告的历史复盘脚本不属于快速开始或公开 CI 的入口。
