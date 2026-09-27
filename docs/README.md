# 工程文档

首次阅读请从以下页面开始：

- [快速开始](QUICKSTART.md)：离线检查、完整本地运行、公开语料摄取。
- [架构](ARCHITECTURE.md)：查询流程与数据职责。
- [语料](CORPUS.md)：来源、获取、许可与 fixture 边界。
- [数据声明](DATA_NOTICES.md)：保留的第三方摘录归属。
- [开发贡献](../CONTRIBUTING.md)：修改与验证要求。

## v0.2 规划与工程治理

以下内容均为 **PROPOSED / awaiting Human Review**，不代表已接受决策或已发布功能。当前里程碑及下一人工门禁见 [HANDOFF](../HANDOFF.md)。

| 当前任务 | 按需阅读 |
| --- | --- |
| 产品范围、路线、里程碑与漂移检查 | [v0.2 Blueprint](V02_BLUEPRINT.md) |
| 技术取舍、责任方向、后续架构问题 | [v0.2 Foundation](V02_FOUNDATION.md)，结合当前 [Architecture](ARCHITECTURE.md) |
| 选择开发方法、AI 自主边界与人工接受 | [AI Development Playbook](AI_DEVELOPMENT_PLAYBOOK.md) |
| 提交、PR、CI、评测门槛、版本与发布审计 | [Engineering Governance](ENGINEERING_GOVERNANCE.md) |
| 单个功能实现 | 后续已接受的 Feature Spec + 相关 ADR；本轮尚无 Conversational RAG Feature Spec |

本页复用为文档地图，不另建同义 index。AGENTS 只保留规则和导航；HANDOFF 只保留当前状态；Blueprint 管产品范围；Foundation 管取舍；Architecture 管实际职责；Spec 管单功能行为；治理文档管跨切片约束；ADR 只记录已接受的长期决定，候选留在 Foundation；一次性 Plan 不替代长期知识。

其余 specs、ADR 与带版本前缀的文件是实现演进记录，保留当时的名称、配置和判断，不能用作最新安装入口或当前产品成绩。历史机器报告与原始实验产物不随源码发布；引用这些本地报告的历史复盘脚本不属于快速开始或公开 CI 的入口。
