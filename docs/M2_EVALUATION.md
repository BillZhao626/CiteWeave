# M2 评测方法与复现

## 冻结数据

`evals/public-standards-v1.json`：48 个原创问题，24 dev / 24 test；6 类题型，包括直接事实、多证据、跨文档、不可回答、边界和定位。所有问题在第一次调用模型前创建并以 `.sha256` 冻结。没有根据测试结果调题或修改排序参数。

三份真实 PDF：RFC 2119（1997）、RFC 3339（2002）、NIST SP 800-145（2011）。问题只针对这些历史文档中的内容，不能当作最新标准建议。manifest 记录下载 URL、官方身份、2026-09-14 获取日期、文件哈希和许可说明。RFC 官方旧 PDF 链接获取失败后使用 ETSI 公共参考库；NIST 使用官方原件。原 PDF 留在 `.runtime/evaluation/corpus/`，不进入公共候选文件。

RFC 3339 的 ETSI 渲染版物理页与印刷页码不同。gold 使用 **零起始 PDF 物理页索引**，以及原件哈希、block_id、Unicode codepoint span 和精确 quote；浏览器显示物理页索引 + 1。gold 的 passage 由多个行级 span 组成，反映完整参考论据。有限标注不是所有可能支持片段的穷举。

题目由 AI 对照原文编写，并检查 PDF 渲染页面；不能标为全量人工标注。项目所有者已对 001/008/027 的实际答案及给出的参考摘要完成人工复核，原始标签、方法和来源见 `evals/reviews/m1-baseline-human.json`。这不是全量 PDF 的独立人工复标。

## 指标及分母

- Retrieval：binary relevance Recall/MRR/nDCG @6/@20/@40。相关项是覆盖 gold span 的实际 chunk ID；重复 ID 去重，空召回计 0，无 gold 的不可回答题返回 null，不混入可回答题分母。
- Dense/BM25：同时保留每版本 raw ranking 和分数。跨文档汇总采用该分路各版本排名的 RRF，不能直接混加文档局部 BM25 分数。RRF 和 reranked 是产品实际融合/重排次序。
- Evidence：gold 进入初始召回并集、RRF 前 20（reranker input）、最终前 6 的覆盖率分开计算。line-based M1 配置可能拆散事实，覆盖率不能等同语义完整度。
- Answer：版本化 `prompts/judge-v1.txt`，保存 DeepSeek model、参数、Prompt hash、逐次 usage 和费用。correctness/completeness/faithfulness/relevancy/refusal correctness 分开。无有效 final 的请求按系统失败计 0；没有事实断言的拒答在 faithfulness 上记 null。Judge 失败/未评审数量与分母必须可见。
- Citation：先通过授权 Run → Citation membership → 实际版本 → Blob SHA-256 → 重新解析 PDF → block/span/text/hash/每个 box 的校验，才能算 grounded。其后，precision/recall 衡量与有限 gold 的重合；其局限是未标注的合理替代证据可能得低分。精确定位通过不代表语义支持自动通过，后者由答案 faithfulness 辅助评审。

报告同时包含 per-case、aggregate、错误与 bad-case attribution。平均值旁保留 denominator；`micro_grounded` 是实际引用条数，不能与有引用的题数混淆。输入/输出费用是固定 rate card 的估算，provider actual charge 始终标 unavailable。

## M1 baseline

首轮在 M1 原 HybridRetriever、chunking、RRF、BGE 和 answer-v1 上运行。`scripts/eval_baseline.py` 只包裹 Qdrant adapter 捕获原始排名，不更改返回结果。该轮的六个关键源文件哈希与实际配置保存在运行工件中。后续 M2 基线比较继续使用相同检索策略，不把可观测性变更宣传为效果提升。

基线 ID：`106987aa-0141-48de-9291-b1492c147b75`。原始工件在 `.runtime/evaluation/runs/<id>/`，通过 `scripts/import_m1_baseline.py` 导入产品 PG catalog，未重复发起问答。`scripts/eval_judge.py --eval-run <id>` 仅评审已保存的答案，有持久费用预留；中断后未知的 Judge 调用不自动重发。

## 产品运行入口

页面“评测”或 `POST /v1/evaluations`，指定知识库、dataset 和 split。知识库必须已摄取 manifest 对应的三份原件；产品不会接收任意远程 URL 或读取任意本机路径。每题走普通 QueryRun，保留失败，后台处理；HTTP 不等待整批结果。

`GET /v1/evaluations/{id}/artifact` 导出机器可读 JSON；`.../report` 返回 Markdown；`.../cases` 分页查询逐题记录。普通回答可跳转 Run Inspector。人工复核可通过授权 `.../cases/{case_id}/review` 保存；不得由 AI 伪造 human label。

测试集比较只用于发现和报告差异，不据此反复选择参数。若以后改变 chunking/模型/检索参数，应先用 dev，记录新 config identity，再执行一次冻结 test 比较。

## 实际 M2 与冻结比较

M2 产品运行 `a32e838b-b5c2-4a6c-b8e7-7aabf2e8f944`：48 Query / 48 Judge 完成，26/26 实际引用重新解析原 PDF 通过。四层逐题事实、Judge usage、Prompt/config 与完整导出保存在本机 `.runtime/evaluation/runs/<id>/artifact.json`；授权产品 API 可再次导出。

使用 `scripts/report_m2_comparison.py --baseline 106987aa-0141-48de-9291-b1492c147b75 --candidate a32e838b-b5c2-4a6c-b8e7-7aabf2e8f944` 从既有 PG 事实生成汇总，不调用模型。公开报告为 `reports/m2-comparison.json` 及 `m2-baseline-{all,dev,test}.md` / `m2-candidate-{all,dev,test}.md`。两轮源版本和共有配置一致，48 题 evidence coverage 无差异；没有按 test 调参。

M2 correctness 均值 0.3229（n=48），completeness 0.2917（n=48）；dev / test correctness 分别 0.2917 / 0.3542（各 n=24）。最终 gold 覆盖 0.2305（n=40），说明现有证据覆盖仍不足。26/26 grounded 仅表示定位完整通过，不等同支持所有回答结论。此轮 human review=0，不能复用 M1 人工标签冒充新的复核。

M2 QueryRun created_at → completed_at 中位数 1350.4 ms、p95 1754.1 ms；原 runner latency 含评测准备，且 aggregate 的 p50 使用排序后上中位项，comparison 使用 statistics.median，故两者不同。M1 在 Windows harness、M2 在 container worker，时间数字不是受控性能比较。逐题 query_embedding / QueryRun 时长中位比例 3.315%，暂不新增缓存，见 ADR 0004。

M2 Query 估算 ¥0.01326494、Judge ¥0.04341988；两者 actual charge 均 unavailable。完整费用范围、引用指标分母、限制与数据见 M2_ACCEPTANCE.md。单次 Judge 分数差异不作为改进结论。
