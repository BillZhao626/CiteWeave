# 第三方来源台账

本项目业务逻辑、测试 fixture、开发问题集、实验脚本独立编写。公开依赖和 UI registry 组件不属于个人独占版权，保留上游许可证。

| 来源 | 用途 | 声明 |
|---|---|---|
| intfloat/multilingual-e5-small | 本机 embedding | MIT；revision `614241f622f53c4eeff9890bdc4f31cfecc418b3` |
| BAAI/bge-reranker-v2-m3 | 本机 reranker | Apache-2.0；revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` |
| shadcn/ui 官方 registry | Web button 组件 | MIT；CLI 依赖解析失败后直接读取官方 registry JSON，引入原样组件，许可证保留在 apps/web/SHADCN-LICENSE.md |
| ReportLab STSong-Light | 原创 PDF fixture 字体引用 | 使用库提供的标准 CID 字体名称，不复制 Windows 字体文件 |
| Mozilla PDF.js / pdfjs-dist 6.3.289 | 原始 PDF 渲染、CMap、标准字体和 wasm | Apache-2.0；prepare_web.py 同步包内 LICENSE 到构建产物，辅助资源保持原样 |
| React Router / TanStack Query / Zod 等 npm 包 | 路由、服务端状态、运行时契约 | 使用公开 npm 发行包；版本以 pnpm-lock.yaml 为准，完整依赖许可证待发布前汇总 |
| 其他 PyPI / npm / Docker 依赖 | 框架、驱动、运行时 | 版本由锁文件/digest 记录；正式发布前生成 SBOM 与许可证清单 |

模型权重、缓存和运行日志默认忽略。M1 原创示例 `apps/web/public/original-handbook.pdf` 纳入候选文件，可由 `scripts/make_m1_fixture.py` 再生；内容为虚构观测站采样规则，不含私有/3GPP 原件或 Windows 字体文件。浏览器截图仅含本项目原创界面和材料。私有审计目录不属于开源导出范围。当前不发布远程仓库、不添加暗示全部权属审核完成的许可证声明。

## M2 新增来源与设计参考

M2 未新增运行时依赖；继续使用现有锁定框架和驱动。治理、Trace、评测、可靠性及 UI 业务代码独立实现，未复制外部项目业务源码。

| 来源 | 使用范围与权利边界 |
|---|---|
| [Celery Tasks 官方文档](https://docs.celeryq.dev/en/stable/userguide/tasks.html) | 参考 acknowledgement、任务幂等和有界 I/O 的语义；本项目 PG lease/fence/reconcile 为独立实现 |
| [PostgreSQL pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html) | 自定义格式 dump / restore 的官方操作说明；本项目在短暂停写后复制 Blob，与空 Qdrant 一起演练 |
| [Qdrant Collections](https://qdrant.tech/documentation/manage-data/collections/) | collection 管理接口；归属证明、引用保护与审计决策由 CiteWeave 自己实现 |
| RFC 2119 / RFC 3339 / NIST SP 800-145 | 真实评测语料；逐文件 URL、hash、获取日期及许可说明以 `evals/public-standards-v1.json` 为准。只公开清单、原创问题和有限参考片段，原始 PDF 不纳入候选 |
| DeepSeek 公开 API / 费率文档 | 版本化 Judge 和 rate card 的接口依据见 costs.py、prompts/judge-v1.txt；估算不等于实际账单 |
| Docker 官方仓库问题报告 | 本机 socket 故障诊断参考，链接和可逆处置边界记录于 M2_OPERATIONS.md；不是产品运行依赖 |

截至 2026-09-15 的候选检查仅匹配本机正在使用的管理员、数据库、模型网关、Provider 密钥，不能替代通用 secret detector、法律审查或 M3 完整 SBOM。人工复核文件仅保存项目所有者给出的三条标签与理由，不包含第三方个人资料。
