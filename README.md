# CiteWeave · 让每条引用回到原文

**Production-oriented open-source evidence-grounded RAG engine · 0.3.0-alpha.1**

个人独立实现的证据化知识库引擎，面向单人本机部署。将 PDF 摄取、中文混合检索、流式问答、精确引用、开发者复盘、批量评测和版本恢复串成一条可验证的工程链路。**M3 COMPLETE：本地开源候选验收通过。** 不宣称企业生产就绪或通用业务准确率。

```text
创建知识库 → 上传 PDF → 持久摄取 → Dense + 中文 BM25 → RRF → BGE 重排
→ 有界相邻原文补全 → DeepSeek 流式回答 → 引用校验 → 原 PDF 字符高亮
                        ↘ Run Inspector / 同题对比 / 版本治理 / 故障恢复
```

引用绑定不可变文档版本、原文字符范围和坐标。PostgreSQL 保存业务事实；租约与 fencing 避免部分索引发布；Qdrant 可以从 PG + BlobStore 重建，Valkey 消息丢失不等于业务任务丢失。

## 快速开始

验证环境：Windows / PowerShell 7 / Python 3.12 / Node ≥22.20 / pnpm 11.19 / Docker Desktop / 16 GB RAM / RTX 4060 Laptop 8 GB。本地 E5/BGE 模型，生成使用个人 DeepSeek API。首次需下载依赖、模型和镜像。CPU-only 与 Linux 一键入口尚未验收。

```powershell
# 在启动环境配置个人 DEEPSEEK_API_KEY，不写入源码、前端变量或日志。
.\scripts\m1.ps1 -Setup         # 首次安装锁定依赖、固定 revision 模型并启动
.\scripts\m1.ps1 -Action Up     # 后续启动当前版本
.\scripts\m1.ps1 -Action Verify # 真实数据库/检索模型 + 模拟 LLM 的回归门禁
.\scripts\m1.ps1 -Action Stop   # 保留容器、卷和文档
```

脚本名沿用历史版本以保留已有数据卷，运行内容是当前 M3。打开 [工作台](http://127.0.0.1:18080/)，用本机生成的 `.env` 中 `CW_ADMIN_TOKEN` 登录。创建知识库，上传页面提供的原创示例 PDF，等待可提问，再问：“湖畔观测站的温度传感器多久采样一次，原始数据保留多久？”点击引用核对原件，从回答记录进入 Inspector。详见 [安装与恢复](docs/M3_OPERATIONS.md)。

## 能力与技术栈

| 能力 | 实际实现 |
|---|---|
| 有据问答 | SSE 草稿与最终答案分离；按 run / immutable version / span 授权，PDF.js 字符高亮 |
| 检索复盘 | Dense、BM25、RRF、实际重排输入、BGE 排序、最终证据及相邻片段来源 |
| 质量闭环 | 冻结 Dev/Test、人工参考对照、版本化 Judge、坏案例归因、基线/候选逐题对比 |
| 版本治理 | rebuild、显式 rollback、引用保护、GC dry-run 与幂等维护审计 |
| 可靠性 | 持久恢复、fencing、有界超时/重试/取消、共享熔断、单 GPU FIFO、未知费用保留预算 |
| 恢复能力 | PG + 内容寻址原件备份，空 Qdrant 重建后重新解析历史引用 |

后端：FastAPI / Pydantic / SQLAlchemy 2 / Alembic / PostgreSQL 18 / Valkey 8.1 / Celery 5.6 / Qdrant 1.16。检索：multilingual-e5-small + 中文 BM25 + RRF + BGE reranker v2-m3。前端：React 19 / TypeScript 6 / Vite 8 / Router / TanStack Query / Tailwind 4 / shadcn。API-first，OpenAPI 自动生成前端类型；没有新增无关基础设施。

## 真实质量证据

3 份历史英文标准 PDF、27 个物理页面、869 个原文片段；48 个中文问题，Dev/Test 各 24。相同版本与 Judge v4，对比真实 M2 输出和选定 C2。C2 只给已有六个种子补充有界同页原文，保留模型、召回预算、重排器和 answer-v1。

| 指标 | M2 Dev → C2 Dev 复验 | M2 Test → C2 正式 Test |
|---|---|---|
| 最终有限 gold 覆盖 | .2383 → .5358，n=20 | .2227 → .5083，n=20 |
| Judge 正确性/完整度均值 | .3125 → .5833，n=24 | .3261，n=23 → .7045，n=22 |
| 正确性成对变化 | 7 提升 / 17 持平 / 0 退步 | 9 提升 / 12 持平 / 0 退步 / 3 不可比 |
| C2 原 PDF 引用校验 | 50/50 | 59/59 |

Test 的 3 道不可比来自 Judge 引用支持校验失败，保留原始失败，不重复采样补分。定位通过不等于语义完全支持；Test 仍有 3 个事实句被 Judge 判为无支持，有限 gold 引用精度下降，p95 从约 1.83 秒增至 3.54 秒。首次 C2 Dev 分数 .6522（n=23），独立复验 .5833（n=24），同时公开而不挑选最高分。见 [完整指标、实验与代价](docs/M3_BENCHMARK.md)。

24 道用户提交的 AI 辅助人工参考成功校验导入：7 正确、1 部分、16 错误/不当拒答。v1 一致率 21/24；v4 流水线 24/24，其中 20 道是确定性拒答规则，只有 4 道是 LLM 评估，不能写成“LLM Judge 准确率 100%”。

后端 64 项、前端 4 项回归通过；真实 worker SIGKILL 恢复 3/3。隔离恢复重建 16 个版本、验证 52 个 CAS 文件与 333 条历史引用，保留 221 个 QueryRun，用时 130.89 秒。这些是本机验收数据，不是持续容量或异地容灾保证。

![同一道问题的基线与候选答案](docs/images/m3-comparison.png)

## 文档

- [架构](docs/M3_ARCHITECTURE.md) · [API](docs/M3_API_USAGE.md) · [OpenAPI](contracts/openapi.json)
- [评测方法](docs/M3_EVALUATION.md) · [Benchmark](docs/M3_BENCHMARK.md) · [实验日志](docs/reports/m3-experiments.json)
- [运行/恢复/发布](docs/M3_OPERATIONS.md) · [能力限制](docs/M3_LIMITATIONS.md) · [贡献指南](CONTRIBUTING.md)
- [来源记录](docs/PROVENANCE.md) · [第三方许可](THIRD_PARTY.md) · [标准摘录声明](docs/DATA_NOTICES.md) · [SBOM](docs/reports/m3-sbom.cdx.json)
- [M1 历史验收](docs/reports/M1_ACCEPTANCE.md) · [M2 历史验收](docs/reports/M2_ACCEPTANCE.md)
- [M3 完整验收](docs/reports/M3_ACCEPTANCE.md) · [实际演示](docs/M3_DEMO.md) · [源码与证据审计](docs/reports/m3-release-audit.json) · [发布清单](docs/reports/m3-manifest.json)

## 开源边界

原创业务代码、文档和原创示例使用 [MIT](LICENSE)；依赖、模型和标准摘录保留各自权利。初期规划曾进行旧项目评审，因此不声称严格 clean-room 或未经核验的“100% 无权属争议”。后续实现使用本项目新代码/规格与公开资料，不混入旧单位源码、内部资料或凭证。

原始第三方 PDF、`.env`、运行数据、模型缓存和私有审计不进入发布候选。使用经过扫描的独立源码包创建公开仓库，不要上传整个工作目录。298 个已安装组件的许可台账与 CycloneDX SBOM、活跃凭证检查及 Gitleaks 扫描分别记录；它们不是完整法律审计或漏洞认证。API 费用为估算，实际扣费 unavailable。当前未创建或推送远程仓库。
