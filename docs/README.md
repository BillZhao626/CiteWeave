# 工程文档

CiteWeave 是面向技术文档的证据问答工作台。最新正式发布为 [v0.2.0](https://github.com/BillZhao626/CiteWeave/releases/tag/v0.2.0)；`main` 持续开发发布后的 Unreleased 改进。当前产品入口如下，历史文件中的阶段状态、授权与计数仅属于记录时点。

## 当前产品与开发

| 入口 | 内容 |
| --- | --- |
| [快速开始](QUICKSTART.md) | 锁定依赖、离线检查、隔离服务烟测、Windows 本地工作台、停止与备份 |
| [架构与职责](ARCHITECTURE.md) | 查询与摄取、History/State 与 Current Evidence、数据权威、可靠性与检查页面 |
| [API](API.md) | 当前会话、结果、Trace、Context、Publication 与 Operations 路由；生成类型 |
| [运行可靠性](V02B_RUNTIME_RELIABILITY_M1.md) | 幂等、有限 retry、UNKNOWN、取消、fencing 与显式恢复的实现记录和验证 |
| [可观察性与恢复](V02B_OPERATIONAL_OBSERVABILITY_M2.md) | 持久 Trace、阶段诊断、只读 inspection 与隔离恢复测试 |
| [并发测量](V02B_CONCURRENCY_PERFORMANCE_M3.md) | SQLAlchemy Session/Connection Pool、PostgreSQL 共享读锁、本地合成测量及复现限制 |
| [发布验证记录](V02_RELEASE_READINESS.md) | v0.2.0 发布前的源码检查与真实服务烟测；属于该发布的历史记录 |
| [贡献指南](../CONTRIBUTING.md) | 原创与许可、契约、迁移、测试、提交与公开审计 |
| [语料](CORPUS.md) / [数据声明](DATA_NOTICES.md) / [第三方声明](../THIRD_PARTY_NOTICES.md) | 官方来源、哈希、原创 fixtures 与再分发边界 |
| [项目来源](PROVENANCE.md) | 个人独立实现与非公开材料排除边界 |

## 设计与历史记录

设计接受不等于功能已经实现或当前运行已获得授权。历史付费预算不可用于新执行；当前安装与默认可用性以[快速开始](QUICKSTART.md)为准。

| 记录 | 阅读范围 |
| --- | --- |
| [产品范围](V02_BLUEPRINT.md) / [技术基础](V02_FOUNDATION.md) | 产品目标、长期取舍与路线 |
| [会话设计](V02_CONVERSATIONAL_RAG_ARCHITECTURE.md) / [首个切片](specs/07_V02_First_Conversational_Slice.md) | Conversation/Turn/Run、状态提交、上下文与证据边界的设计基线 |
| [评测方法](specs/08_V02_Conversational_Evaluation.md) / [比较协议](V02_COMPARISON_PROTOCOL.md) | 人工接受的比较方法与执行限制 |
| [开发方法](AI_DEVELOPMENT_PLAYBOOK.md) / [工程治理](ENGINEERING_GOVERNANCE.md) | 任务、审阅、验证与交付约束 |
| [架构实现历史记录](history/ARCHITECTURE_IMPLEMENTATION_RECORDS.md) | 原 ARCHITECTURE 的实施增量、旧授权与当时验证；原文保留 |
| [上下文与证据 ADR](adr/0007-memory-and-documentary-evidence.md) / [有界上下文 ADR](adr/0008-bounded-conversational-context.md) | 历史意图与文档事实支持的类型边界 |
| [可靠性 ADR](adr/0023-runtime-reliability-and-recovery.md) / [Trace ADR](adr/0024-operational-trace-and-recovery-inspection.md) | 有效结果幂等、失效结果阻断与持久诊断 |
| [事务 Session ADR](adr/0025-acceptance-evidence-session.md) / [共享读锁 ADR](adr/0026-shared-conversation-scope-readers.md) | 连接池与锁争用修复及不变约束 |
| [解释输入 ADR](adr/0027-production-interpretation-wire-origins.md) / [历史投影 ADR](adr/0028-bounded-accepted-history-projection.md) / [历史相关性 ADR](adr/0029-explicit-candidate-history-relevance.md) | 精确来源、轻量只读投影与显式相关来源选择 |
| [运行观察 ADR](adr/0030-read-only-runtime-observations.md) / [发布检查 ADR](adr/0031-read-only-publication-and-reliability-inspection.md) / [上下文检查 ADR](adr/0032-read-only-context-observations.md) | 可复用、认证且只读的检查页面与观察可用性 |

其余带版本前缀的 Spec、ADR、计划和复盘保留各自历史时点，不替代当前产品描述。原始机器报告、下载语料、模型、数据库和本地运行记录不随源码发布；依赖这些本地产物的复盘脚本不是公开安装或 CI 入口。