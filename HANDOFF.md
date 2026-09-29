# Current milestone

Status: **ACCEPTED — Human Local Calibration Execution Review incorporated** · 2026-09-29

- 当前公开实现：`v0.1.0`，发布提交 `d29a324a06c07799a11ed642e370c5e6d5a2e6db`；v0.2 仍 DESIGNED，Implementation **NOT_STARTED**。
- 已接受基线：Blueprint / Foundation / Governance（[PR #1](https://github.com/BillZhao626/CiteWeave/pull/1)）、Conversational Architecture（[PR #2](https://github.com/BillZhao626/CiteWeave/pull/2)）、Feature / Evaluation 方法论 / ADR 0006–0009（[PR #3](https://github.com/BillZhao626/CiteWeave/pull/3)）、[Calibration Plan](docs/V02_CONVERSATIONAL_CALIBRATION_PLAN.md)（[PR #4](https://github.com/BillZhao626/CiteWeave/pull/4)）。这些设计接受不代表已实现；本地执行仅限下述 PR #5 的独立授权，Evaluation comparison protocol 仍 NOT EXECUTABLE。
- 本次人审落实起点：干净的 `751ba783fa86b538519ea116f4802e85dee3b2c8`，沿用 PR #5 的 `docs/v0.2-local-calibration-execution` 分支；Product Owner 于 2026-09-29 作出 APPROVED WITH REQUIRED CLARIFICATIONS，仅文档落实。
- [Bounded Local Calibration Execution Plan](docs/V02_LOCAL_CALIBRATION_EXECUTION_PLAN.md) **ACCEPTED — Human Local Calibration Execution Review incorporated**：授权恰好一次未来 `local-first-01`，六族/十 target views，必做 M01/M03/M04 可执行部分/M07-pre；M02 仅可选标签查询。上限 elapsed 240 分钟、工程 120 分钟、人审 12 units/96 分钟、local compute 15 分钟/900 CPU-seconds/512 MiB；最多一个小计量入口和四个受控产物。65536 UTF-8 bytes 仅为测量/fixture 安全上限，每族 ≤16 历史 Turns 仅为编写/人审上限；两者均非产品参数或产品证据。当前未执行、未创建产物或适配器。
- Lean 仍是选定的最大 campaign 框架；**LOCAL-FIRST / PROVIDER-OFF-BY-DEFAULT**。仅上述未来本地批次已授权，执行 **NOT STARTED**；provider **0 calls / 0 CNY**，有限 CNY 授权 **NONE / PENDING**；baseline-only pilot **NOT AUTHORIZED**；RES 未释放。
- 启动前须完整记录精确修订的 accepted commit / reviewer / date / start-time。Reviewer 为 Product Owner，日期 2026-09-29，接受的修订 SHA 由 PR #5 记录，start-time 尚未指定；本轮不启动，也不等待另一 Human Review。M05 真实输出、M06 真正会话查询与 M07-runtime 留独立 Gate/真实切片验证，不用静态标注冒充已验证能力。
- 本地退出条件达成即结束前置本地校准并准备独立 Comparison Protocol Freeze；**不能直接开始实现**：Feature/Evaluation 要求独立的实现前 Comparison Protocol Freeze Human Gate 及实现授权，本文保留该顺序。本地成功可为 LOCAL BATCH DONE / CAL PARTIAL / Comparison BLOCKED，不追加测量只为清空 PENDING。
- 最终 N/C/K、selector、Rewrite、各 token caps/output reserve、I/O/期限/质量阈值/比较 arms/repeats 仍 UNFROZEN。文档检索基线不变；Summary、vector/长期 Memory、Tool Runtime/MCP 不进入本轮。
- 交付边界：一个文档 commit 推送至 PR #5，受影响文档检查及一次 Windows/Linux CI 终态成功后标为 Ready for Review，供 owner 最终合并审阅；不 merge/tag/release，不等待 Human Review，不运行校准、provider、产品或旧 RAGFlow 资源。私人审计/旧代码/sealed 数据保持隔离。
- 导航：[文档地图](docs/README.md)、[Feature](docs/specs/07_V02_First_Conversational_Slice.md)、[Evaluation](docs/specs/08_V02_Conversational_Evaluation.md)、[Playbook](docs/AI_DEVELOPMENT_PLAYBOOK.md)、[Governance](docs/ENGINEERING_GOVERNANCE.md)。
