# Current milestone

Status: **ACCEPTED — Human Calibration Plan Review incorporated** · 2026-09-29

- 当前公开实现：`v0.1.0`，发布提交 `d29a324a06c07799a11ed642e370c5e6d5a2e6db`；v0.2 实现仍 **NOT_STARTED**。
- 已接受基线：Blueprint / Foundation / Governance（[PR #1](https://github.com/BillZhao626/CiteWeave/pull/1)）、Conversational Architecture（[PR #2](https://github.com/BillZhao626/CiteWeave/pull/2)）、首个 Feature、Evaluation 方法论、ADR 0006–0009（[PR #3](https://github.com/BillZhao626/CiteWeave/pull/3)）。PR #3 Human Review 日期 2026-09-28，审阅提交 `aa5755cbf70e552827f03211d2770a4dcff3626f`；Feature/ADR APPROVED，Evaluation **APPROVED AS METHODOLOGY / NOT YET EXECUTION-FROZEN**。接受记录不改写为已实现能力。
- 本次起点：沿用 PR #4 的 `docs/v0.2-calibration-plan` 分支，从干净的 `a4bc54be8411e867fff11c173d75f92498fa602d` 开始；原计划 main 基线为已合并 PR #3 的 `7e5b952b2effc32bfa096dfd5297354a0dda5893`。
- Human Calibration Plan Review（2026-09-29，审阅提交 `a4bc54be8411e867fff11c173d75f92498fa602d`，记录见 [PR #4](https://github.com/BillZhao626/CiteWeave/pull/4)）：[Cost-Aware Calibration Plan](docs/V02_CONVERSATIONAL_CALIBRATION_PLAN.md) **APPROVED — with Owner-selected Lean configuration**。Lean 是默认最大资源框架，不是即时资源开放；Recommended 未预授权，Ceiling 仅参考、未授权。升级需独立 Human Budget Expansion Gate，证明 Lean 仍 INCONCLUSIVE、HIGH VOI 的未解问题阻塞具体工程决定且不是未修复缺陷/协议错误造成。
- 当前姿态：**LOCAL-FIRST / PROVIDER-OFF-BY-DEFAULT**。校准执行 **NOT AUTHORIZED**；provider 授权 **0 calls / 0 CNY**，有限人民币额度 **NONE / PENDING**；baseline-only pilot **NOT AUTHORIZED YET**。只有本地证据证明必要且官方身份/容量/价格、计量路径与有限最坏费用及 owner 明确 CNY ceiling 齐备，才可申请独立 provider 授权。
- 已接受 mandatory review、每 arm×primary category 至少一个普通成功项加剩余 10% 分层抽样的初始政策、Lean 人审/工程上限及早停/序贯淘汰；RES 每次由 owner 明确批准释放，不扩大延期架构，不因失望结果追加。界内证据不足返回 INCONCLUSIVE，不自动扩样/调用/repeats/tier。
- 下一精确阶段：**v0.2 Bounded Local-First Calibration Execution Planning / Authorization**。只准备 M01–M07 中无需产品实现可执行的本地有界任务，不可用能力记 unavailable；本轮不开始下一阶段、不执行校准，不夹带 provider pilot、比较、实现或调参。校准不选 winner；独立 **Comparison Protocol Freeze Human Gate** 仍 pending，接受精确数据、baseline、N/C/K/caps、arms/repeats、质量规则、预算、人审及实现范围后才能另行授权候选比较。
- **UNFROZEN / UNSELECTED**：N/C/K、history/state/input/output/interpretation caps、candidate I/O、产品期限/重试预算、样本量、quality/noninferiority/material-similarity margins、repeats 与精确 arms。无实验胜者，Summary、vector Memory、长期记忆和 Tool Runtime 仍排除。
- 本次只追加一条文档 commit 并推送至 PR #4，核验当次 Windows/Linux CI；通过后标为 Ready for Review，供 owner 最终合并审阅。不执行校准，不实现产品/harness/schema/migration，不调用 provider，不改 Feature/Evaluation/ADR 或 runtime/retrieval/prompts/tests，不 merge/tag/release，不等待另一 Human Review。私人审计、sealed 内容与旧 RAGFlow 资源保持隔离。
- 入口：[文档地图](docs/README.md)、[Feature](docs/specs/07_V02_First_Conversational_Slice.md)、[Evaluation 方法论](docs/specs/08_V02_Conversational_Evaluation.md)、[开发方法](docs/AI_DEVELOPMENT_PLAYBOOK.md)、[Git / 发布门禁](docs/ENGINEERING_GOVERNANCE.md)。
