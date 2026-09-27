# Current milestone

Status: **PROPOSED / awaiting Human Review** · 2026-09-27

- 稳定公开基线：`v0.1.0`，起始 main 为 `d29a324a06c07799a11ed642e370c5e6d5a2e6db`。
- 当前：v0.2 Blueprint + Foundation + Engineering Governance 文档提案；本轮 review 分支为 `docs/v0.2-blueprint-governance`，以 Draft PR into main 为人工审阅面。创建 PR 不等于接受，历史实现和指标不改写。
- 入口：[文档地图](docs/README.md)、[产品范围与待决事项](docs/V02_BLUEPRINT.md)、[技术方向及 ADR 候选](docs/V02_FOUNDATION.md)、[Git / 发布门禁](docs/ENGINEERING_GOVERNANCE.md)。
- 约束：不实现 Conversational RAG、不改 schema / 检索 / runtime、不调用付费 provider、不改 GitHub 保护、不 merge、不 tag / Release；私人审计、历史报告和旧 RAGFlow 资源保持隔离。
- 下一步 Human Gate：Product Owner 在本 Draft PR 审阅并明确接受 / 修改范围、责任方向、开发方法与拟议发布标准。接受记录应指向所审文档版本 / commit；提案仍保留 PROPOSED，直到人工决定后再更新。
- 只有基线获接受且下一轮获授权后，才开始 `v0.2 Conversational RAG Architecture Design`；本轮不提前设计。Feature Spec、详细 API / schema、状态生命周期、预算、数据集与 rubric 仍待后续门禁。
