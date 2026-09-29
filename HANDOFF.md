# Current milestone

Status: **Comparison Protocol ACCEPTED — Human Comparison Protocol Review incorporated** · 2026-09-29

- [Comparison Protocol](docs/V02_COMPARISON_PROTOCOL.md)已获 Product Owner **APPROVED**，实现前 Human Gate 已完成；接受单点 AB0 保守默认、未来最大比较/人审预算与 DEFERRED fail-closed 处理。后续结构性实现及 fake-provider/local L1 可单独授权，本次不授权或启动任何阶段。v0.2 Implementation **NOT_STARTED**；当前公开实现仍为 `v0.1.0`。
- 本地结论仍为 **LOCAL BATCH DONE / CAL PARTIAL / Comparison BLOCKED**。恢复收尾已记录于 PR #6 / `96e8e584744a9e89f3d3566f1bbb5e694eb5c13c`；提案从干净工作树开始，收据身份已核对。停止前置 Calibration；不启动 Development/Regression/provider 或产品实现。
- 接受的执行契约来自 [PR #5](https://github.com/BillZhao626/CiteWeave/pull/5)，修订提交 `7e0fc836d09ef6bd62759b5a1f9e58530eddaf73`，合并基线 `f66e7d94dd63b2597257dc7a0f5e267cb98c612f`。原 `local-first-01` 收据封存失败的历史记录保留不变。
- Product Owner 独立授权的一次 `local-first-01-recovery-01` 已成功，以字节完全相同的固定 manifest 持久化 M01/M03/M04 可执行部分/M07-pre。六族十视图人审已完成（10 units/5 分钟，无阻塞争议）；F4.V1 为纠正前基线。恢复未新增人审或改变测量语义。
- 唯一适配器为 [measure_v02_local_calibration.py](scripts/measure_v02_local_calibration.py)：使用安全环境 allowlist，先持久化核心结果，再封存可选元数据；保留网络/子进程保护。收尾仅纳入该已验证脚本及当前导航，不重新运行 Calibration。
- 原批次与恢复批次的 manifest/receipt/report/index 均保留在 ignored `.artifacts/v02-calibration/`，不随公开仓库提交。详细结果和身份仍由本地收据追溯；本页不替代原始证据。
- 本地退出条件已满足，停止前置本地 Calibration，不为清空 PENDING 追加测量。M02 SKIPPED；M05/M06/M07-runtime 仍不可用或延期。Provider 0 calls / 0 CNY，baseline pilot NOT AUTHORIZED；无 PG/GPU/cloud/RES 使用或产品执行。
- 65536 bytes 与每族 16 历史 Turns 仅为工作量边界。N/C/K 保守默认及 selector、Rewrite、I/O、质量规则、arms/repeats 已按协议人审接受，非实测最优或 winner；token caps/output reserve、真实计量/期限/支付身份仍 DEFERRED/PENDING。Comparison Freeze 后仍需独立实现授权，比较须另有完整执行身份及有限预算。
- 导航：[文档地图](docs/README.md)、[执行契约](docs/V02_LOCAL_CALIBRATION_EXECUTION_PLAN.md)、[Feature](docs/specs/07_V02_First_Conversational_Slice.md)、[Evaluation](docs/specs/08_V02_Conversational_Evaluation.md)、[Playbook](docs/AI_DEVELOPMENT_PLAYBOOK.md)。已接受 Feature/Evaluation/ADR/Architecture 语义不变。
