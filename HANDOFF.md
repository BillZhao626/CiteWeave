# Current milestone

Status: **ACCEPTED — Human Review incorporated** · 2026-09-27

- 稳定公开基线：`v0.1.0`，起始 main 为 `d29a324a06c07799a11ed642e370c5e6d5a2e6db`。
- 当前：v0.2 Blueprint / Foundation / Governance 已按 Product Owner 的 APPROVED WITH REQUIRED CHANGES 决议接受；[PR #1](https://github.com/BillZhao626/CiteWeave/pull/1) 在 `docs/v0.2-blueprint-governance` 落实决议，供 owner 最终合并审阅。历史实现和指标不改写。
- 入口：[文档地图](docs/README.md)、[产品范围与接受记录](docs/V02_BLUEPRINT.md)、[技术方向及 ADR 候选](docs/V02_FOUNDATION.md)、[Git / 发布门禁](docs/ENGINEERING_GOVERNANCE.md)。
- 约束：不实现 Conversational RAG、不改 schema / 检索 / runtime、不调用付费 provider、不改 GitHub 保护、不 merge、不 tag / Release；私人审计、历史报告和旧 RAGFlow 资源保持隔离。
- 本轮停止点：决议落实、文档提交推送、最新双平台 CI 通过后将原 PR 置为 Ready for Review；合并由 owner 单独决定，不循环等待新的人工审阅。
- 合并后的下一授权规划阶段：`v0.2 Conversational RAG Architecture Design`；本轮不开始。Architecture 尚不存在且未接受；Feature Specs、Evaluation Spec、ADR、详细 API / schema、状态生命周期、预算、数据集与 rubric 仍待后续门禁。实现状态：**NOT_STARTED**。
