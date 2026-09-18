# M2 — Production Core：现状审计与实施计划

2026-09-14。M1 manifest 的 135 个候选文件逐一哈希一致；Git 未署名提交，无 remote。只审计 CiteWeave 自身，未读取旧单位源码或私有审计材料。

| 工作包（均属于 M2） | 已有基础 / 缺口 | 实施与验证 |
|---|---|---|
| 评测基础与 M1 baseline | M0 synthetic 实验；无真实 PDF 数据集和批量 runner | 3–5 份可追踪公开 PDF、约 48 题、dev/test 固定；先保持 M1 算法和 Prompt 跑 baseline，再做后续变化 |
| Trace 与 Inspector | QueryRun 已存在，只有 20 个重排候选，无阶段耗时；job 有状态事件 | 扩展现有 Run，保存全部有界候选及阶段摘要；同源 API 和 React Inspector，不增加遥测基础设施 |
| 索引与版本治理 | 每版本仅一个 ingestion job；每次尝试隔离索引，缺 GC/rebuild/rollback | 增量 migration、索引登记/保护/审计；显式文档 rollback；rebuild 不改变原件与 evidence identity；真实备份恢复演练 |
| 请求可靠性 | 单 query / 单模型推理，部分 retry/usage；无 breaker、错误分类和公平排队 | 有界策略、可观察 breaker、取消传播、逐尝试 usage；受控并发负载决定缓存是否值得加入 |
| 产品与总验收 | 只有知识库工作台 | Runs、Evaluation、Versions、系统/任务状态；原 M1 故障回归、完整门禁、浏览器验收和真实结果报告 |

核心约束：不修改 RRF / BM25 / chunking 来改善 baseline；测试集在运行前冻结，不按其结果改题或调参。保留原件、字符坐标、版本绑定和 fence 发布。旧 RAGFlow 保持停止，不操作其数据。新公开数据原件只放被忽略的 .runtime/evaluation/corpus；公开候选仅包含 manifest、原创题目和有依据的标注。

主要风险：M1 line-based chunk 可能把跨行事实拆开；跨文档 BM25 分数不可直接比较；GC 与查询/回滚存在竞争；rebuild 若复用独立 job 的 fence 数会命名冲突；失败/取消后费用可能不确定；16 GB RAM 需要限制后台评测与 GPU 并发。上述风险用显式契约和针对性测试处理，不通过无限重试、假 final 或扩大结果声明掩盖。

预计模块：新增 evaluation/、trace、reliability、lifecycle、operations 与相应 schema/测试/脚本；增量修改 domain、catalog、ingestion_state、hybrid、answering、LLM/model adapter、API 和 React 路由。保持现有合理目录。M1 报告/原 manifest 保留，不覆盖为 M2 结果。

完成标准采用本轮用户给出的 16 条整体验收条件；只在全部通过后标记 M2 COMPLETE，完成后停止，不自动进入 M3。
