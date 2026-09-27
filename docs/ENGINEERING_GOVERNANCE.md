# Git / PR / Release Governance

Status: **PROPOSED / awaiting Human Review** · 2026-09-27

本页是待审提案，不宣称远端保护已启用或 v0.2 已获接受。产品范围见 [Blueprint](V02_BLUEPRINT.md)，工作方法见 [Playbook](AI_DEVELOPMENT_PLAYBOOK.md)。本轮只提交文档、push 并创建 Draft PR；不 merge、不改保护、不 tag、不创建 GitHub Release。

## 本轮仓库与文档审计

2026-09-27 通过 Git fetch / GitHub API 读取：

- 本地工作树起始干净，所在分支 `main`；HEAD、`origin/main`、解引用的 `v0.1.0` 均为 `d29a324a06c07799a11ed642e370c5e6d5a2e6db`。公开仓库默认分支为 main。
- [v0.1.0 Release](https://github.com/BillZhao626/CiteWeave/releases/tag/v0.1.0) 已公开，非 draft / prerelease，发布时间为 2026-09-25。现有包 / API 的历史 `0.3.0a1` / `0.3.0-alpha.1` 标识与公开发行版本不同，见 [QUICKSTART](QUICKSTART.md)；本轮不修改这些冻结标识。v0.2 发布前必须审阅版本映射与兼容说明，不能假装已经统一。
- [该提交 CI](https://github.com/BillZhao626/CiteWeave/actions/runs/36022514759) 的 `Offline checks (ubuntu-latest)` 与 `Offline checks (windows-latest)` 均 success；这是已观测的公开离线证据，不是多轮、GPU、provider 或生产容量证据。
- main 的 `protected=false`，branch protection 查询返回 404 “Branch not protected”，repository rulesets 列表为空；本次成功读取不属于“无权限无法判断”。Squash / merge commit / rebase 三种合并均允许，自动删除合并分支未开启。这里只记录快照，不声称持续监控。
- 既有入口为根 README、CONTRIBUTING、AGENTS 和 docs/README；ARCHITECTURE / QUICKSTART 描述当前实现。M1/M2/M3 文档与 ADR 保留历史约束；部分旧报告链接指向不随源码发布的本地产物，不适合作为新治理门禁的公开证据。
- 没有公开 HANDOFF；旧 `docs/*CHECKPOINT.md` 被 gitignore 排除。本轮新增简短公开 HANDOFF，不复制历史检查点或私人报告。复用 docs/README，不另建同义 docs/index，不迁移或重编号旧 ADR。

## Git 生命周期

main 表示已经接受、可公开展示的状态，不意味着每个 merge 都是稳定发行。实质功能从更新后的 main 开短生命周期分支；一个分支对应一个可解释结果，尽早建立 Draft PR，避免永久 dev 分支。

| 分支 | 用途 / 例子 | 退出 |
| --- | --- | --- |
| `docs/<outcome>` | `docs/v0.2-blueprint-governance` | 文档审阅通过后合并 |
| `feat/<outcome>` | `feat/session-follow-up` | 一个已接受 Spec 的可验收切片 |
| `fix/<outcome>` | `fix/citation-version-resolution` | 复现、根因与回归证明 |
| `release/<version>` | `release/v0.2.0` | 可选的短期 release audit / 文档收口；修复仍经 PR 入 main，最终从 main 发布 |

禁用 dev、test2、final2、codex 这类无结果信息的名字。维护者和 AI 使用同一规则；本项目明确命名优先于工具默认前缀。合并后确认无需继续工作，再删除工作分支；不删除标签和主分支。共享 review 后优先追加提交；确有必要重写个人分支时先协调并用 force-with-lease，不能 force-push main。

一次 commit 通常是一项自洽逻辑变化，能说明动机与验证范围；相关 Spec + 实现 + 测试可同提交，互不相关内容必须分开。无需每个小 commit 重跑全仓；提交说明例如 `feat(conversation): preserve follow-up constraints`、`fix(citations): retain source version`、`docs(v0.2): propose conversational RAG roadmap and engineering governance`。不要把碎片保存点或混杂改动包装成最终提交。

实质变更进入 main 必须 PR；默认小修也走轻量 PR，无需大模板。一个 PR 对应一个可审阅结果，正文包含问题 / 前后行为、范围与非目标、关联 Spec / 人工决定、测试命令及真实结果 / skips、文档影响、AI 行为证据（如涉及）、ADR / 迁移 / 恢复影响（如涉及）和剩余限制。与范围无关的栏位写“不适用”即可。

默认 **Squash Merge**：main 一条提交对应一个 PR 结果，保留 PR 链接及作者归属；分支上的调试提交不要求变成主线历史。Squash 比 merge commit 更适合当前单人维护和独立结果；rebase merge 仅在保留多个独立提交本身有评审价值时作为明确例外。采用线性历史保护时不使用 merge commit。

## 受影响验证与普通 PR Gate

| 变化 | 提交前的最小验证 | PR 合并前 |
| --- | --- | --- |
| 纯文档 | diff / 空白、改动文档的本地链接、事实与状态、发布 allowlist / 秘密检查 | 同样检查 + 现有 Windows / Linux CI；无需在本机再跑 runtime 矩阵 |
| 后端 / API | 受影响 Ruff lint / format、单元测试；OpenAPI 变化重新生成前端类型并检查 | 双平台离线 CI；相关集成与契约检查 |
| 前端 | lint、typecheck、build 及有意义的组件 / 流式行为测试 | 双平台离线 CI，用户路径证据 |
| 数据 / 任务 / scope | Alembic 与真实隔离服务测试；升级、重试、幂等、取消、stale attempt、部分索引等受影响风险 | 双平台 CI + 相应集成证据，不能用 mock 推出真实服务已通过 |
| AI 行为 / prompt / memory | 预注册的 dev 对照、profile 身份、人工错误审阅与受影响回归 | AI Gate 证据；不把每个 PR 当作开启 sealed holdout 的理由 |

普通 PR 的必要条件：范围及必要人工决定可追溯；没有未解决的阻断问题；受影响检查和**最新候选**的两个离线 CI job 成功；差异只有预期文件；文档 / 契约 / notices 相符；失败和 skips 明示并解释。纯文档 Draft PR 可以先等待 CI 与人工审阅，不得因此 merge。CI 工作流目前无路径过滤，push / PR 自然执行既有离线检查；本提案不修改它。

阻断项不能以“后续补测”通过普通 PR：授权或引用身份回归、秘密泄露、错误最终发布、持久状态损坏、未被接受的行为 / 责任变化。其他未覆盖项需说明影响，不得把缺失测试标作通过。离线入口为 `uv run --frozen python scripts/check_release.py`，它执行后端 lint / format / 非 integration 测试、前端 typecheck / lint / Vitest / build 及生成契约校验；真实服务 / provider 不在其覆盖内。

## v0.2 Eval Gate：先冻结，再实现与调参

以下数量与阈值是**本次待接受的项目目标**，不是行业标准或实测成绩。接受后如需改变，必须留下理由、影响和人工决定；不能看到候选结果后降低门槛再声称同一次评测通过。数据与 rubric 在对应 Feature Spec 接受阶段建成并冻结，本轮不生成数据或执行模型调用。若不可行，应在调参前修改提案。

| 必须覆盖的主要分层 | 判定关注点 |
| --- | --- |
| Coreference | 正确绑定实体；有歧义时澄清，不猜测 |
| Rewrite fidelity | 不增添事实，不丢否定、条件、时间、实体、版本或查询范围 |
| Topic shift | 新话题不继承无关限制；显式回到旧任务时恢复相关约束 |
| Relevant history | 找回完成当前任务所需的历史，记录其来源 |
| Historical noise | 无关历史、错误旧回答与恶意指令不覆盖用户当前意图或授权 |
| Old-but-relevant | 跨干扰轮次仍能取回旧而相关信息 |
| New-but-irrelevant | 更新但无关的信息不挤掉更相关历史；与上一层做配对对照 |
| Long conversation | 超过窗口、接近 / 超过预算时上下文仍有界，compaction 后保留关键限制 |

建议最小集合：dev、regression、sealed confirmation 各 40 个会话场景，每个主要分层至少 5 个，各场景只计一个主要分层但可有辅助标签；另设至少 24 个单轮回归问题，覆盖可回答、证据不足、版本 / scope 与引用到 PDF。按任务 / 实体 / 对话模板族分组拆分，避免同一对话改写跨集合泄漏。旧而相关 / 新而无关配对留在同一 split。全部使用原创或明确许可材料，标注人工 / AI 辅助来源，保留归属；不默认复用历史 sealed test / holdout。

在 protocol 中预注册：数据版本与字节哈希、每层数量、标注与争议处理、期望行为、baseline、评分脚本 / rubric 版本、模型 / prompt / profile、环境、种子 / 重复次数、预算及候选选择规则。dev 用于调参；regression 作固定守门，不以反复选参替代 dev；独立 confirmation 在一个候选冻结后才开启，失败后保留结果并回到 dev，不能把看过的数据继续声称未见确认集。

行为按场景 pass/fail 计：该场景所有预设关键轮次与预期行为都满足才 pass；基础设施失败、超时、缺输出均计 fail，同时另报失败原因。RC / stable 要求 regression 和 confirmation **各自总通过率 ≥90%，各主要分层 ≥80%**；完整最终结果或预期澄清 / 拒答的完成率 **≥95%**，分母为全部计划执行场景，不剔除失败。多次执行的计分规则必须事前冻结，不能只选最好的一次；报告数量、区间和合成数据局限，不宣称通用准确率。

单轮以相同数据、语料 / 版本、模型条件将候选与固定 v0.1 基线做配对比较，正确性和完整性评分量表为 [0,1]，各自平均差值 **≥ -0.03**；报告配对数量与不确定性、全部失败，不能把不存在的历史评测当作基线或只比较成功样本。多轮还应有受控的 Recent-Turn-only 简单对照，证明复杂记忆的必要性；具体对照配置在 Spec 冻结，不改变 v0.1 检索语义。

所有发行阶段均有零容忍否决项：越权或跨会话泄漏、范围静默扩大、最终引用身份 / span / PDF 不可解析、未验证草稿成为最终、丢失或重复有效持久结果、新增关键事实错误。最终引用物理解析率必须 **100%**；语义支持另由 rubric 与人工检查，不用引用合法性代替正确性。

RC / stable 的评分须包含维护者对 regression / confirmation 所有预定义关键轮次输出的人工复核，并审阅全部失败、Judge 分歧和上述零容忍案例；Judge 只能辅助，缺失判断记 N/A 并阻断相应质量 gate。保存可公开的去敏摘要、失败 ID 与证据定位；不公开私人会话、完整 provider error body、密钥或无许可文档。

上下文必须按已接受的 token 上限有界（包括历史、摘要、证据、输出预留）；压缩、溢出和 fallback 行为均须验收。每轮调用次数、费用、延迟及整会话最大预算的具体数值，须在 Feature Spec / protocol **实现前**冻结，后续全部 gate 引用该版本；缺少预算不是 release pass。本轮不虚构硬件测量数值。

## 版本、tag 与 GitHub Release

采用 [SemVer 2.0.0](https://semver.org/)；0.x 仍属初始开发，本项目额外承诺：破坏既有公共行为要显式披露、审阅并给迁移说明，不能借 0.x 静默破坏。`v0.2.1` 用于 v0.2 兼容修复，不夹带新一轮架构 / 产品范围；按风险跑受影响回归，若触及对话策略 / 模型 / 数据职责则重新满足相关完整 gate。1.0 前明确公共兼容面。已发布标签与产物不可改写；修复用新版本。

| 阶段 | 精确进入条件 | GitHub 表达 |
| --- | --- | --- |
| 普通 merge | 上述普通 PR Gate + 所需人工接受 | Squash 入 main；无 tag / Release |
| 内部 milestone | 对应 Done 与证据齐备 | PR / issue / HANDOFF 检查点；不因文档或阶段完成 tag |
| `v0.2.0-alpha.1` | 已接受 Blueprint / Foundation 与所含 Spec；至少一条持久多轮 UI → API → 检索 → 最终引用 → PDF 路径，刷新可继续；双平台 CI、所含能力的集成 / 迁移与 dev / regression 验证、单轮保护和零容忍项通过；干净安装复现已承诺支持面；未完成分层和限制逐项公开；人工接受外部试用 | main 上精确候选打 prerelease tag；GitHub Release 标记 prerelease，说明不满足 stable 全范围 |
| `v0.2.0-rc.1` | v0.2 范围全部完成；全部 8 层 regression / confirmation 和单轮门槛、人工复核、token / 成本预算、Trace、真实服务持久性与失败测试、升级恢复、fresh clone、文档及秘密 / 来源审计通过；无已知 release blocker；候选与配置冻结，人工接受 | prerelease tag + prerelease Release；不把 N/A 当通过 |
| `v0.2.0` | 所有 RC gate 仍对最终候选有效；外部试用发现的 blocker 关闭；精确 main SHA 的双平台 CI 和 release audit 通过；维护者明确接受发布 | 不可变 stable tag + 非 prerelease GitHub Release |

alpha 已包含能力的 regression 分层沿用 ≥80%、其场景总通过 ≥90%、完成 ≥95% 的门槛；未实现能力可明确排除 alpha 声明，不能排除适用于所含路径的安全 / 单轮门禁。后续 alpha / RC 编号递增；失败候选不覆盖旧标签。Release 是对外可复现交付包，不是每个 commit 的日志条目。

## Release audit 与精确提交证据

每个发行候选的 audit 必须列出候选 commit / tree、对应 PR 和人工接受记录、代码 / 配置 / prompt / 数据版本，及以下项的命令、环境、结果和可核对证据链接：

1. 功能路径、Conversation / Run trace 的原问题、改写、状态 / 选中记忆和证据关联；默认 UI 不展示无关内部噪声。
2. 适用行为门槛、单轮 Answer → Citation → Evidence → PDF 回归、失败 / skips / N/A 与真实模型范围；offline、mock、synthetic、人工和真实服务证据分开。
3. 后端 lint / format / 测试、前端 lint / typecheck / tests / build、生成类型一致性、精确提交 Windows / Linux CI。
4. 有 schema 变化时，用隔离环境验证从 v0.1 备份升级、持久重启、重复提交、取消 / worker loss 等相关状态风险；验证备份恢复及版本兼容。没有可行降级时明确 forward-fix / 备份恢复，不承诺无损 downgrade。
5. 对拟发布提交执行 fresh clone + 锁定依赖的公开离线入口；完整运行验证当前声明支持的 Windows 环境与原创新实例路径。Linux 离线 CI 不提升为 Linux 完整部署支持。release-relevant 安装脚本变化须重新验证。
6. README、当前架构、运行 / feature 文档、版本映射、已知限制与实际实现一致；检查公开文件 allowlist、待发布 Git 历史、secret / license / 第三方归属，报告扫描范围和限制。

发布顺序：release 修复先经 PR 合入 main → 固定最终 SHA → 在该 SHA 上核对 CI / audit → 人工接受该 SHA → tag → GitHub Release。稳定 tag 必须解引用到这一已接受的 main 提交，不能指向未合并 release 分支。发布前再次读取 main；若前进则明确选择重做最终候选审计，不能悄悄改 tag 目标。

PR CI 的测试合并提交、功能分支 HEAD、Squash 后 main SHA 可能不同，不能互换其身份。证据始终记录实际被测 SHA；无运行时差异时可在 audit 中基于 tree / 路径差异说明哪些旧证据仍适用，但最终 main 的 CI 与 fresh-clone 检查仍须通过。任何运行时、prompt、数据、依赖或迁移变化，都要重跑受影响 gate；最终候选与已看过 confirmation 的关系必须透明，不冒充新的未见评测。

Release notes 包含用户变化、支持 / 非目标、安装 / 升级 / 恢复步骤、版本映射、已知限制、候选 SHA、PR / audit / CI / 评测证据及来源说明。数据或模型未随包发布时写清获取与授权要求。若证据未公开，提供可公开摘要与可核对的身份，不把私人文件路径当作公众可复现实证。

## main 保护建议（只提案）

建议采用一个针对 main 的 active branch ruleset，或表达同等约束的 classic protection：要求 PR、解决讨论、线性历史，禁止 force push 与删除；要求 `Offline checks (ubuntu-latest)` 和 `Offline checks (windows-latest)`（预期来源 GitHub Actions），候选须与最新 main 兼容并更新后通过检查。不要配置不存在的 job 名，不要求未部署的 CI。建议默认只开放 squash merge，并在确认分支退出后自动删除已合并分支。

当前 solo 阶段建议 **required approvals = 0**，不强制 CODEOWNERS / “另一人批准最近 push”；PR 作者不能批准自己的 PR，要求 1 位外部批准会把日常维护锁死。人工门禁改由维护者在 PR 中针对文档版本 / SHA 明确留下接受记录，AI 不可代填；它是治理约束，不等于 GitHub 独立 reviewer 保障。将来有第二位常驻维护者再启用 1 approval 与 stale approval dismissal。依据见 [GitHub review 限制](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/approving-a-pull-request-with-required-reviews)。

正常流程不使用 admin / bypass。Ruleset 建议无常规 bypass actor；classic 保护要显式覆盖管理员。唯一维护者仍能更改设置，因此不能声称绝对无法绕过；紧急恢复若必须临时解除约束，记录原因、操作者、范围、前后设置与 SHA，完成后恢复保护并补 PR / audit，不能以 bypass 掩盖质量失败。规则含义以 [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) 与 [rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) 为准。本轮不实际设置这些选项。

## Revert / 回滚

普通缺陷经 fix 分支 / PR，紧急阻断可以对 main 的 squash commit 创建 revert PR，保留原因、失败案例与受影响回归。不重置公开 main、不删除或移动已发布 tag；坏 release 标记已知问题并给新 patch / prerelease。

代码 revert 不等于数据回滚。涉及会话或索引变更，先按已接受 migration / 恢复方案停写并备份 PostgreSQL 与 blobs，再选择兼容旧版本、forward fix 或恢复；Qdrant 可重建、Redis 可恢复，不把删除卷作为升级方案。不触碰旧 RAGFlow 资源，不运行全局 Docker prune / reset。
