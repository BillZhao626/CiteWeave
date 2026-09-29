# Current milestone

Status: **PROPOSED — awaiting Human Calibration Plan Review** · 2026-09-29

- 当前公开实现：`v0.1.0`，发布提交 `d29a324a06c07799a11ed642e370c5e6d5a2e6db`；v0.2 实现仍 **NOT_STARTED**。
- 已接受基线：Blueprint / Foundation / Governance（[PR #1](https://github.com/BillZhao626/CiteWeave/pull/1)）、Conversational Architecture（[PR #2](https://github.com/BillZhao626/CiteWeave/pull/2)）、首个 Feature、Evaluation 方法论、ADR 0006–0009（[PR #3](https://github.com/BillZhao626/CiteWeave/pull/3)）。PR #3 Human Review 日期 2026-09-28，审阅提交 `aa5755cbf70e552827f03211d2770a4dcff3626f`；Feature/ADR APPROVED，Evaluation **APPROVED AS METHODOLOGY / NOT YET EXECUTION-FROZEN**。接受记录不改写为已实现能力。
- 本次起点：PR #3 已合并；2026-09-29 fetch 后 `main` / `origin/main` / HEAD 均为 `7e5b952b2effc32bfa096dfd5297354a0dda5893`，工作树干净。授权任务为有界 **Calibration Plan Freeze** 规划，不是执行。
- 当前提案：[Cost-Aware Calibration Plan](docs/V02_CONVERSATIONAL_CALIBRATION_PLAN.md)。定义最便宜测量、候选范围推导、E1–E12 激活/延期、分层预算和三档容量、早停、人审/工程约束、校准产物及 Comparison Gate。三档资源上限均待 owner 选择；官方模型/价格/生成 tokenizer 与精确 token/人民币额度待补齐，本次 provider 调用/花费为 0。
- 下一步：Human Calibration Plan Review 选择 tier、测量范围、人审/工程容量和可选 baseline-only pilot；计划接受后校准本身仍须另行有界授权。校准只测分布/固定基线，不选 winner。证据具备后独立 **Comparison Protocol Freeze Human Gate** 接受精确数据、配置、阈值、重复及预算，才能另行授权实现/候选比较。
- **UNFROZEN / UNSELECTED**：N/C/K、history/state/input/output/interpretation caps、candidate I/O、产品期限/重试预算、样本量、quality/noninferiority/material-similarity margins、repeats 与精确 arms。无实验胜者，Summary、vector Memory、长期记忆和 Tool Runtime 仍排除。
- 本次只交付一条文档 commit、Draft PR 及当次 Windows/Linux CI 核验；不执行校准，不实现产品/harness/schema/migration，不生成完整多轮集，不调用模型、不改 GitHub 保护、不 merge/tag/release，不等待或反复轮询 Human Review。私人审计、sealed 内容与旧 RAGFlow 资源保持隔离。
- 入口：[文档地图](docs/README.md)、[Feature](docs/specs/07_V02_First_Conversational_Slice.md)、[Evaluation 方法论](docs/specs/08_V02_Conversational_Evaluation.md)、[开发方法](docs/AI_DEVELOPMENT_PLAYBOOK.md)、[Git / 发布门禁](docs/ENGINEERING_GOVERNANCE.md)。
