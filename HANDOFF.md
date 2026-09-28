# Current milestone

Status: **PROPOSED — First Feature / Evaluation / ADR package ready for Human Review** · 2026-09-28

- 当前公开实现：`v0.1.0`，发布提交为 `d29a324a06c07799a11ed642e370c5e6d5a2e6db`。
- 当前：v0.2 Blueprint / Foundation / Governance 已完成 Human Review 并接受；[PR #1](https://github.com/BillZhao626/CiteWeave/pull/1) 是该接受基线的交付与审阅记录。历史实现和指标不改写。
- 入口：[文档地图](docs/README.md)、[产品范围与接受记录](docs/V02_BLUEPRINT.md)、[技术方向及 ADR 候选](docs/V02_FOUNDATION.md)、[Git / 发布门禁](docs/ENGINEERING_GOVERNANCE.md)。
- 约束：不实现 Conversational RAG、不改 schema / 检索 / runtime、不调用付费 provider、不改 GitHub 保护、不 merge、不 tag / Release；私人审计、历史报告和旧 RAGFlow 资源保持隔离。
- 当前架构：[v0.2 Conversational RAG Architecture](docs/V02_CONVERSATIONAL_RAG_ARCHITECTURE.md) 已获 Human Architecture Review **APPROVED**（2026-09-28，审阅提交 `9e6e75baa26f230fd62d30919a1c29fac10434e8`）；[PR #2](https://github.com/BillZhao626/CiteWeave/pull/2) 是架构交付与审阅记录。设计起点为 `242982a`，接受不依赖 PR 是否已合并，也不表示运行能力已实现。
- 本轮起点：PR #2 已合并，fetch 后 `main` / `origin/main` / 起始 HEAD 均为 `0ccb4fc6cbaf6024a10096cf2a9df04bfdef2925`，工作树干净；已接受架构状态保持不变。
- 当前规划包：[首个 Feature Spec](docs/specs/07_V02_First_Conversational_Slice.md)、[初始 Evaluation Spec](docs/specs/08_V02_Conversational_Evaluation.md) 及 [ADR 0006](docs/adr/0006-conversation-state-and-effective-commit.md) / [0007](docs/adr/0007-memory-and-documentary-evidence.md) / [0008](docs/adr/0008-bounded-conversational-context.md) / [0009](docs/adr/0009-conversation-profile-and-trace.md) 均为 **PROPOSED，尚未接受**。首个切片是持久追问 → A+B 历史/解释 → 既有文档 RAG → 有界上下文 → 原子接受/Trace；不依赖 Summary、向量记忆、长期记忆或 Tool Runtime。
- 下一步：Human Feature / Evaluation Review 和四份 ADR 各自 Human Review；再另行授权校准任务，按 Evaluation 的冻结表补齐真实计量、候选范围、预算与有依据的质量容忍度，并在产品实现/调参前接受。当前只完成协议设计，无实验胜者或新参数最优值。
- v0.2 实现状态：**NOT_STARTED**。本轮仅文档交付、Draft PR 与现有 CI，不实现、不调用 provider、不 merge/tag/release，也不循环等待 Human Review。规划包可审阅不等于执行协议已数值完整或实现获授权。
