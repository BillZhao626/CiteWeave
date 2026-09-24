# Third-party notices / 第三方声明

根目录 MIT 只覆盖原创 CiteWeave 代码与原创文档，不替换依赖、标准摘录、模型、字体或其他上游资产的许可。仓库不分发依赖二进制、模型权重、完整第三方标准 PDF、数据库或向量快照。

## 原创资产

- 应用、原创文档和两页 `original-handbook.pdf`：MIT。手册由 ReportLab 生成，使用标准 CID 字体引用，不捆绑系统字体。
- `tests/structure_fixtures.py` 的原创结构样本：CC0-1.0，见对应 fixture README。
- 回答一致性合成样本：原创 MIT 测试材料，不包含私人历史题目。
- 产品界面截图是实际 CiteWeave 画面的区域裁剪，没有重绘产品像素。其中第三方文档摘录继续受其来源条款约束。

## 产品截图与公开标准

README 中两张截图显示 IETF RFC 9114 的少量原文与 PDF 区域。来源：Mike Bishop (ed.), **HTTP/3**, RFC 9114, June 2022, [RFC Editor](https://www.rfc-editor.org/rfc/rfc9114.html)。Copyright (c) 2022 IETF Trust and the persons identified as the document authors. All rights reserved. 适用 [IETF Trust Legal Provisions](https://trustee.ietf.org/documents/trust-legal-provisions/tlp-5/)。截图是问答产品的演示，不是修改后的 RFC 版本，也不表示 IETF 背书。

RFC / NIST 评测短摘录保留出处与位置，并遵循 [docs/DATA_NOTICES.md](docs/DATA_NOTICES.md) 和 [协议来源声明](evals/PUBLIC_PROTOCOLS_HOLDOUT_NOTICES.md)。这些文字不归入软件 MIT 授权。完整标准从官方来源获取，保留原有版权与作者信息。

MQTT 来源：**MQTT Version 5.0**, edited by Andrew Banks, Ed Briggs, Ken Borgendale, and Rahul Gupta, 07 March 2019, OASIS Standard，Copyright © OASIS Open 2019. All Rights Reserved. [官方版本与 Notices](https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html)。仓库的通信评测保留原创问题、释义及来源定位/哈希，不分发原始 MQTT PDF 或批量原文。完整数据获取规则见 [CORPUS](docs/CORPUS.md)。

## 依赖与模型

| 组件 | 上游条款与处理 |
| --- | --- |
| FastAPI、React 等 | 各依赖的原始许可；精确版本见 `uv.lock` 与 `apps/web/pnpm-lock.yaml` |
| PostgreSQL | [PostgreSQL License](https://www.postgresql.org/about/licence/)；用户自行拉取官方镜像 |
| Qdrant | [Apache-2.0](https://github.com/qdrant/qdrant/blob/master/LICENSE) |
| Redis 8 | 保留[上游多许可选择](https://redis.io/legal/licenses/)，包括 AGPLv3；不将 Redis 视为 MIT 组成部分 |
| Celery | [BSD-3-Clause](https://github.com/celery/celery/blob/main/LICENSE) |
| psycopg / psycopg-binary | [LGPL 条款](https://github.com/psycopg/psycopg/blob/master/LICENSE.txt)；未修改、独立安装的库，不移除替换与再链接权利 |
| E5-small | [固定模型版本](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3) 的 MIT 元数据；只下载到本地缓存 |
| BGE reranker v2 m3 | [固定模型版本](https://huggingface.co/BAAI/bge-reranker-v2-m3/tree/953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e) 的 Apache-2.0 元数据；不分发权重 |
| PyTorch / CUDA | PyTorch 与 NVIDIA 各自条款；锁定 wheel 不等于将全部组件授权为 MIT |
| PDF.js | [Apache-2.0](https://github.com/mozilla/pdf.js/blob/master/LICENSE) 及字体 / wasm 附带声明；`prepare_web.py` 复制时保留 LICENSE 与资产目录 |
| shadcn/ui | 保留 [SHADCN-LICENSE.md](apps/web/SHADCN-LICENSE.md) |

`python scripts/prepare_web.py` 从实际安装的 npm 包生成 `apps/web/public/THIRD_PARTY_NOTICES.txt`，并将其随前端构建发布。生成目录与依赖缓存不提交 Git。构建者另行分发容器、模型或依赖二进制时，须遵守对应上游条款；源码 MIT 不替代这些义务。
