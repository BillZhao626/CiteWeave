# CiteWeave M3 演示路径

使用 [安装说明](M3_OPERATIONS.md) 启动本地工作台。凭证只在个人电脑读取，不录入演示稿或截图。下面两条路径分别适合全新安装与当前保留评测记录的开发环境。

## 全新安装：原创中文文档

1. 登录，创建知识库，上传页面提供的原创观测站示例 PDF。
2. 等待摄取状态 READY，提问：“湖畔观测站的温度传感器多久采样一次，原始数据保留多久？”
3. 核对回答中的“30 秒”和“7 天”，点击引用检查原 PDF、页码与字符高亮。回答措辞可能随模型变化。
4. 从回答记录进入 Run Inspector，查看 Dense、BM25、RRF、实际重排输入和最终证据，以及调用耗时、token 和费用估算。
5. 在系统与任务页查看摄取、版本和维护状态。故障恢复用验收报告讲解；正常展示无需现场杀进程。

## 质量改进：同题对比

当前开发环境保留正式 Test：候选 EvalRun `d2c953cc-e6b2-4f65-8fe4-1c650a4f6f4a`，基线 `e6aedb3a-5977-4164-988c-1bbd0aca40d9`。全新安装不会自带这些数据库记录；可直接阅读公开比较报告，或按 [评测说明](M3_EVALUATION.md) 建立新的运行。

1. 打开评测，选择候选 Test，再选择相同数据集、split 和 Judge 的基线。
2. 选择 `cw-public-008`。M2 仅回答 public cloud 面向公众；C2 同时回答设施位于云提供方场所。
3. 打开候选 Inspector：六个重排种子扩展为 25 个有界同页原文片段。相邻片段显示 seed 来源，未重排片段不伪造排序分数。
4. 点击 E11，查看 NIST SP 800-145 原始 PDF 第 7 页的不可变版本和高亮字符。说明“引用位置正确”与“语义支持正确”分别评估。
5. 回到报告，展示失败样本和代价：3 个 Test Judge 结果不可比，p95 增加，有限 gold 引用精度下降；没有隐藏失败或据 Test 继续调参。

![基线与候选同题对比](images/m3-comparison.png)

![运行链路与费用](images/m3-inspector.png)

![原文版本与字符高亮](images/m3-evidence.png)

NIST 摘录：Republished courtesy of the National Institute of Standards and Technology. 来源与使用边界见 [声明](DATA_NOTICES.md)。截图来自实际运行，不是效果稿。

## 展示口径

可描述为“个人独立实现的 production-oriented 证据化 RAG，引入冻结 Dev/Test、受控实验、精确引用和故障恢复验证”。质量数字必须同时交代三份历史英文标准、48 个中文问题、Judge 方法与分母；引用 [Benchmark](M3_BENCHMARK.md) 和 [验收报告](reports/M3_ACCEPTANCE.md)。不宣称通用准确率、企业 SLA、测试覆盖率 85%、效率提升 40% 或 exactly-once。
