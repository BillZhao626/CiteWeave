# Current milestone

Status: **PROPOSED / awaiting Human Architecture Review** · 2026-09-28

- 当前公开实现：`v0.1.0`，发布提交为 `d29a324a06c07799a11ed642e370c5e6d5a2e6db`。
- 当前：v0.2 Blueprint / Foundation / Governance 已完成 Human Review 并接受；[PR #1](https://github.com/BillZhao626/CiteWeave/pull/1) 是该接受基线的交付与审阅记录。历史实现和指标不改写。
- 入口：[文档地图](docs/README.md)、[产品范围与接受记录](docs/V02_BLUEPRINT.md)、[技术方向及 ADR 候选](docs/V02_FOUNDATION.md)、[Git / 发布门禁](docs/ENGINEERING_GOVERNANCE.md)。
- 约束：不实现 Conversational RAG、不改 schema / 检索 / runtime、不调用付费 provider、不改 GitHub 保护、不 merge、不 tag / Release；私人审计、历史报告和旧 RAGFlow 资源保持隔离。
- 当前审阅产物：[v0.2 Conversational RAG Architecture Proposal](docs/V02_CONVERSATIONAL_RAG_ARCHITECTURE.md)，设计基于核实后的 `main` / `origin/main` = `242982a`。状态为 PROPOSED，尚未接受；涵盖身份、状态生命周期、有效轮次、记忆/证据边界、兼容、备选与 ADR 候选。
- 下一门禁：Human Architecture Review，在对应 Draft PR 针对精确提交留下决定。通过后才进入获授权的 Feature Spec / Evaluation Spec 与 ADR 接受流程；API/schema、交互、预算、数据/rubric 等见提案的明确延期表。v0.2 实现状态：**NOT_STARTED**；本轮不等待人工决定，不进入实现。
