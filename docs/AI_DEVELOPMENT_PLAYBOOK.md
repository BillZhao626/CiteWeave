# AI Development Playbook

Status: **PROPOSED / awaiting Human Review** · 2026-09-27

本提案须经人工接受后生效；当前不授权 v0.2 实现。工程不变量见 [AGENTS](../AGENTS.md)，产品范围见 [Blueprint](V02_BLUEPRINT.md)，合并 / 发布证据见[工程治理](ENGINEERING_GOVERNANCE.md)。

## 按问题选择方法

| 任务 | 方法 | 最小有用产物 |
| --- | --- | --- |
| 产品 / 架构 | SDD（先定义规格）+ Design Review + Human Gate | 用户问题、边界、备选、风险、Done 与接受记录 |
| 正常功能 | Vertical Slice + SDD + TDD | 一个端到端结果；先以有意义的行为失败案例约束实现，再补异常与回归 |
| AI 行为 | Eval-driven + Human Review | 调参前冻结数据划分、rubric、门槛、预算；dev 对照、人工错误分析与独立确认 |
| Bad Case | Root Cause Analysis + Controlled Replay | 保存输入 / profile / 状态 / 证据身份，定位首个错误阶段，一次控制一个变量 |
| 重构 | Regression-first | 先证明关键外部行为，再改内部结构；不混入隐式语义变化 |
| 发布 | Release Audit | 对精确候选提交核对功能、质量、迁移、干净安装、来源、限制与批准 |

错字、链接、低影响可逆编辑不强制新 Spec、ADR、TDD 或全仓测试。现有缺陷的最小修复只补能防止真实回归的测试，不写照抄实现的断言。

## 人工决定与自主执行

Blueprint 接受、重要架构责任边界、Feature Spec 行为、新的长期 ADR、发布标准变更必须人工决定；对外 release promotion 也须显式接受。记录格式：决策主题、审阅的文档版本 / commit、接受 / 拒绝 / 有条件接受、条件、决策人、日期及 PR / issue / 已授权对话记录链接。若决定来自本地对话，维护者确认后在 PR 记载可公开的摘要，不公开整段私人会话。

AI 可以建议，不能代替人填写 Accepted。CI 通过、无回复、普通 commit、合并导航文档都不构成上述决定。接受基线后，正常编辑、受影响测试、调试和逻辑完整的提交无需逐步请示；push / PR 等动作依照该任务已授权范围执行。越过已接受范围或遇到必须由人决定的冲突时，先完成可审阅提案再停在相应门禁。

实施循环：Plan → Edit → Test → Observe → Repair → Update status → Continue。直到已接受里程碑的 Done 满足或遇到真实阻塞；不因一次测试成功跳过验收，也不重复无变化的 preflight。诊断先读当前错误及相关源文件，不默认重读历史评测档案。

## 只加载相关上下文

从 [docs/README](README.md) 选择入口：范围问题读 Blueprint；责任取舍读 Foundation / 当前架构 / 相关 ADR；单功能读对应 Spec；坏例读该 Run 与对应 protocol；发布读工程治理、当前运行说明和候选证据。历史 M1/M2/M3 文档按需查契约，不把其阶段停止语句、缺失本地报告或旧成绩变成当前里程碑。

每个实现里程碑先完成 Blueprint drift check。HANDOFF 只写当前状态、约束与下一步；接受记录和长期决策留在 PR / Spec / ADR，失败与真实 skips 留在验证证据，不写成长篇状态日记。
