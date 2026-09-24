# 公开语料与数据边界

仓库发布原创代码、原创 fixtures、公开来源元数据，以及带来源标注的评测定义。它不包含雇主、银行、客户或历史私人语料，也不包含完整第三方标准 PDF、模型权重、向量、数据库和批量原文导出。

## 七份产品示例文档

| 来源 | 官方入口 |
| --- | --- |
| RFC 9293 | [Transmission Control Protocol](https://www.rfc-editor.org/info/rfc9293/) |
| RFC 9114 | [HTTP/3](https://www.rfc-editor.org/info/rfc9114/) |
| RFC 9110 | [HTTP Semantics](https://www.rfc-editor.org/info/rfc9110/) |
| RFC 9846 | [RFC Editor](https://www.rfc-editor.org/info/rfc9846/) |
| RFC 9673 | [RFC Editor](https://www.rfc-editor.org/info/rfc9673/) |
| RFC 9175 | [RFC Editor](https://www.rfc-editor.org/info/rfc9175/) |
| MQTT 5.0 | [OASIS Standard，2019-03-07](https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html) |

精确标题、版本、来源 URL、页数和 SHA-256 在 [source manifest](../corpus/public_telecom_manifest.json)。使用：

```powershell
uv run --frozen python scripts/fetch_public_telecom.py
```

下载保存于忽略的 `.runtime/private/public-telecom`，脚本验证字节数、哈希及首页身份。不同字节会报错，不自动换版。哈希绑定可复现字节，不代替出版方签名。保存原始版权声明，上传时填写对应来源许可；不要把标准文档标成原创手册的 MIT。

## 资产分类

| 资产 | 发布处理 |
| --- | --- |
| CiteWeave 源码、原创文档 | 根目录 MIT |
| 原创两页 handbook | MIT；由 `scripts/make_m1_fixture.py` 生成，不嵌入操作系统字体 |
| 结构解析与一致性测试 fixtures | 结构样本为 CC0-1.0，一致性样本为 MIT；合成内容不证明真实语料质量 |
| 当前产品截图 | 原始产品图的区域裁剪；RFC 原文摘录保留其来源权利，参见第三方声明 |
| RFC / NIST 评测定义与复核材料 | 原创问题、注释及有归属的短摘录；保留 [data notices](DATA_NOTICES.md) 和[协议来源声明](../evals/PUBLIC_PROTOCOLS_HOLDOUT_NOTICES.md) |
| MQTT 相关评测 | 原创问题、来源标识与定位信息；不分发完整 MQTT 原文或 PDF |
| 模型与依赖 | 仅发布引用、版本与 lockfile；由用户自行下载，适用各上游许可 |

公开来源辅助制作的评测标注并非独立人工 Gold。历史复核材料中保留的测试身份只是对应标注的技术关联，不构成当前产品成绩。下载与摄取说明见 [QUICKSTART](QUICKSTART.md)。
