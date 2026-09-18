# ADR 0004 — M2 的诊断、生命周期与可靠性边界

日期：2026-09-16。状态：Accepted，已由 M2 实测验收。

## 问题

M1 已证明不可变原件、租约/fence 和独立尝试索引可以组合成完整问答链路。但普通请求只保存重排候选，不能解释上游失败和证据丢失；历史索引没有清理与恢复入口；缺少真实公开 PDF 评测；本地模型拒绝并发请求，没有公平排队。

## 决策

| 主题 | 决策 | 替代方案与理由 | 代价 / 替换触发条件 |
|---|---|---|---|
| Trace 存储 | 扩展现有 QueryRun，JSONB 保存有界候选、阶段和逐次调用摘要；问题与片段受 owner 权限保护，不保存完整 Prompt/请求头 | 不增加第二套 Run 模型，也不引入独立遥测集群；当前单机吞吐不需要 | 阶段写入增加 PG 往返；运行量增长、跨服务追踪需求出现后接入 OpenTelemetry/exporter，保留业务 Run identity |
| Circuit breaker | PG 中两个小状态行：DeepSeek 和本地模型。事务锁串行化状态，半开只允许一个有期限的探测，generation 拒绝过期探测结果 | 单进程字典不能协调 API 与 worker；Redis 不作为业务事实。当前不需要复杂分布式框架 | 每次逻辑调用增加 PG 往返；PG 不可用则失败关闭。更多 provider/区域需要独立作用域与指标 |
| 并发 | 单 GPU 推理槽、FIFO 最多 4 个等待者、8 个 HTTP handler、等待 8 秒、读请求 5 秒；worker concurrency=1，每个模型批次结束释放槽 | 不增加 GPU 副本或直接同时跑 E5/BGE；先实测当前 8 GB GPU | 已开始的 GPU kernel 无法被客户端取消瞬间中断；最多继续完成一个有界 batch。独立 GPU/高吞吐需求再拆模型服务 |
| GC | 默认 dry-run；先证明索引归属，保护发布指针、有效/待恢复尝试、Run 快照、评测快照、缺少物理映射的历史引用。实际删除逐个执行、幂等、PG 审计 | 不按 collection 名称/年龄直接删除，不启用后台自动 GC | 保守保护会留下旧索引。维护锁与快照/发布/回滚串行；外部删除最多持锁一个有界调用。规模扩大后改持久删除意图与独立维护队列 |
| Rebuild | 同一 immutable version 新建独立 rebuild job，物理索引名含 job UUID + fence；再次解析 PG/Blob 事实并验证原 canonical、chunk IDs、文本、坐标、BM25 一致；原索引继续服务直到发布 | 不覆盖旧 collection；不修改原件或历史 chunk | 解析/模型 revision 变更导致结果身份变化时，必须创建新文档版本，不能伪装 rebuild |
| Rollback | 显式指定目标 READY version 和 expected active version；有正在摄取的新版本时拒绝切换。切换 Document.active_version_id | 不复制历史内容到“最新版本”；不改 Citation 的版本绑定 | 只支持单文档发布切换，没有多文档原子 release。真实 KB release 需求出现时升级 |
| Backup | 短暂停止本项目 API/worker，检查没有未完成工作后 dump PG 并复制不可变 CAS；恢复到 UUID 测试 DB、独立 blob 目录与空 Qdrant，重新建索引和验证引用 | Valkey 不备份为事实；不依赖 Qdrant snapshot 恢复唯一业务数据；不引入 MinIO | 单机短暂停写，备份未提供异地容灾或加密托管。需要更低 RPO/RTO 或多人服务时采用在线备份/PITR/对象存储 |
| Evaluation | 真实 PDF 清单和 48 题冻结；每题关联普通 QueryRun。现有 Celery 每次执行一题，PG 持久调度，失败仍进入分母；Judge 独立预留费用 | 不把评测另做一个 demo，也不在 HTTP BackgroundTasks 中运行长任务 | 测试集很小、与开发集共享文档，结果不代表一般业务。增加领域和独立人工标注后才能扩展效果结论 |

## 缓存决策

决策：不新增通用 query embedding / retrieval / LLM answer cache。已有 immutable canonical artifact 和评测批内 PDF 解析复用继续使用；每条 citation 仍重新检查 Blob hash。

依据 `reports/m2-comparison.json`：48 个真实 QueryRun 的 query_embedding 中位数 44.108 ms，逐题占总时长的中位数 3.315%；总 QueryRun 中位数 1350.4 ms。48 个问题全不重复，当前样本没有可实现的跨题命中。`m2-load.json` 的 12 次重复 embedding 测量约 525 ms，包含 Windows HTTP client 创建成本，不能充当生产请求 GPU 耗时。即使完全消除 embedding 阶段，也只能节省当前这部分耗时，实际缓存还需 lookup 和校验。

替代方案：进程 LRU 简单，但 API / worker 分别缓存且需有界失效；Valkey 共享缓存增加运维、版本键和敏感查询驻留；answer cache 还需 prompt/model/version/config/freshness 身份。当前收益不足以支付复杂度。代价是重复请求仍计算。替换触发：在真实使用中持续观察到足够重复问题、模型排队或该阶段明显成为瓶颈，再用 dev 工作负载验证命中率和端到端收益；缓存键必须包含模型 revision、归一化规则及配置，容量和期限明确。

## 迁移

Alembic 0003 新增 M2 状态表和 QueryRun 字段，取消单版本只有一个 job 的唯一约束，原 ingest job 保留。旧行的 kind 默认为 ingest；旧 QueryRun 的新 Trace 字段为空，不倒推不存在的阶段耗时。0004 增加 Judge 实际费用预留时间，旧记录缺失时明确按创建时间归属。M1 原验收工件保留；新验收使用 m2 前缀。旧版本应用不应在生产数据出现 rebuild job 后继续运行。

## 验证

已新增有意义的指标、breaker、FIFO、Provider retry/cancellation、真实索引 rebuild/rollback/GC 测试。真实恢复、受控负载、浏览器与 worker SIGKILL 回归均已执行，逐项证据见 reports/M2_ACCEPTANCE.md。
