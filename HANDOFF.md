# Current milestone

Status: **ACCEPTED — Human Feature / Evaluation Methodology / ADR Review incorporated** · 2026-09-28

- 当前公开实现：`v0.1.0`，发布提交为 `d29a324a06c07799a11ed642e370c5e6d5a2e6db`。
- 当前：v0.2 Blueprint / Foundation / Governance 已完成 Human Review 并接受；[PR #1](https://github.com/BillZhao626/CiteWeave/pull/1) 是该接受基线的交付与审阅记录。历史实现和指标不改写。
- 入口：[文档地图](docs/README.md)、[产品范围与接受记录](docs/V02_BLUEPRINT.md)、[技术方向及 ADR 候选](docs/V02_FOUNDATION.md)、[Git / 发布门禁](docs/ENGINEERING_GOVERNANCE.md)。
- 约束：不实现 Conversational RAG、不改 schema / 检索 / runtime、不调用付费 provider、不改 GitHub 保护、不 merge、不 tag / Release；私人审计、历史报告和旧 RAGFlow 资源保持隔离。
- 当前架构：[v0.2 Conversational RAG Architecture](docs/V02_CONVERSATIONAL_RAG_ARCHITECTURE.md) 已获 Human Architecture Review **APPROVED**（2026-09-28，审阅提交 `9e6e75baa26f230fd62d30919a1c29fac10434e8`）；[PR #2](https://github.com/BillZhao626/CiteWeave/pull/2) 是架构交付与审阅记录。设计起点为 `242982a`，接受不依赖 PR 是否已合并，也不表示运行能力已实现。
- 规划起点：PR #2 已合并，当时 fetch 后 `main` / `origin/main` / HEAD 均为 `0ccb4fc6cbaf6024a10096cf2a9df04bfdef2925`，工作树干净；已接受架构状态保持不变。本次审阅落实沿用 PR #3 分支，从干净的 `aa5755cbf70e552827f03211d2770a4dcff3626f` 开始。
- Human Review（2026-09-28，审阅提交 `aa5755cbf70e552827f03211d2770a4dcff3626f`，记录见 [PR #3](https://github.com/BillZhao626/CiteWeave/pull/3)）：[首个 Feature Spec](docs/specs/07_V02_First_Conversational_Slice.md) 与 [ADR 0006](docs/adr/0006-conversation-state-and-effective-commit.md) / [0007](docs/adr/0007-memory-and-documentary-evidence.md) / [0008](docs/adr/0008-bounded-conversational-context.md) / [0009](docs/adr/0009-conversation-profile-and-trace.md) 的原设计文本 **APPROVED**；[Evaluation Spec](docs/specs/08_V02_Conversational_Evaluation.md) **APPROVED AS METHODOLOGY / NOT YET EXECUTION-FROZEN**。首个切片范围不变，Summary、向量记忆、长期记忆和 Tool Runtime 仍排除。
- 下一授权规划阶段：**v0.2 Calibration Plan Freeze**。定义精确有界的校准任务，覆盖 N/C/K 候选范围所需分布、真实 tokenizer/context 计量、history/state/input/output 预算候选、candidate I/O limits、必要的 baseline 方差、样本量理由及以后另行授权的 provider 测量范围/费用；本轮不开始该规划阶段。
- 执行边界：校准本身须单独有界授权；校准证据具备后，另经 **Comparison Protocol Freeze Human Gate** 接受具体实验值，才能另行授权候选比较。N/C/K、范围/caps/I/O、样本量、质量/非劣效 margin、repeats、provider 延迟/费用预算及需校准的精确 arms 均 **UNFROZEN / UNSELECTED**；无实验胜者。
- v0.2 实现状态：**NOT_STARTED**。PR #3 的接受不授权产品实现、候选比较、provider/model 评测或参数调优。本轮仅落实审阅、推送文档与核对 CI；通过后供 owner 最终合并审阅，不 merge/tag/release，不等待另一 Human Review。
