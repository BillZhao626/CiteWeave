# Current milestone

Status: **ACCEPTED — Human Architecture Review incorporated** · 2026-09-28

- 当前公开实现：`v0.1.0`，发布提交为 `d29a324a06c07799a11ed642e370c5e6d5a2e6db`。
- 当前：v0.2 Blueprint / Foundation / Governance 已完成 Human Review 并接受；[PR #1](https://github.com/BillZhao626/CiteWeave/pull/1) 是该接受基线的交付与审阅记录。历史实现和指标不改写。
- 入口：[文档地图](docs/README.md)、[产品范围与接受记录](docs/V02_BLUEPRINT.md)、[技术方向及 ADR 候选](docs/V02_FOUNDATION.md)、[Git / 发布门禁](docs/ENGINEERING_GOVERNANCE.md)。
- 约束：不实现 Conversational RAG、不改 schema / 检索 / runtime、不调用付费 provider、不改 GitHub 保护、不 merge、不 tag / Release；私人审计、历史报告和旧 RAGFlow 资源保持隔离。
- 当前架构：[v0.2 Conversational RAG Architecture](docs/V02_CONVERSATIONAL_RAG_ARCHITECTURE.md) 已获 Human Architecture Review **APPROVED**（2026-09-28，审阅提交 `9e6e75baa26f230fd62d30919a1c29fac10434e8`）；[PR #2](https://github.com/BillZhao626/CiteWeave/pull/2) 是架构交付与审阅记录。设计起点为 `242982a`，接受不依赖 PR 是否已合并，也不表示运行能力已实现。
- 下一规划阶段：**v0.2 Feature / Evaluation Specification and ADR Drafting**，尚未开始。下一次人类引导规划确定首个 vertical slice、先冻结的 Feature Spec、初始 Evaluation Spec 结构与实现前所需 ADR 草案；四个 ADR 领域获起草授权，具体文本仍须各自 Human Gate，这四项尚无 Accepted ADR。首个切片不以 Summary、向量记忆、长期记忆或 Tool Runtime 为前提。
- v0.2 实现状态：**NOT_STARTED**，架构接受不授权实现。Feature / Evaluation / Implementation 的延期决定仍有效；本轮仅记录审阅结果，不开始下一规划阶段、不等待另一人工决定。
