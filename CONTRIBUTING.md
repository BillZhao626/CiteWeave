# 参与开发

先用 issue 描述可复现问题、修改范围与验证方法。贡献须为原创或具有兼容授权并保留署名；原创贡献遵循 MIT。不要提交雇主／团队内部代码、保密文档、凭据或模型权重。

修改前阅读 AGENTS.md、[当前架构](docs/ARCHITECTURE.md)与受影响 Spec/ADR。保持不可变文档版本、精确证据偏移、检索范围与任务语义；前端 API 类型由 Pydantic/OpenAPI 生成。持久 schema 变更使用 Alembic；新的 prompt/profile 需要明确身份，不能重解释旧 Run。

按[快速开始](docs/QUICKSTART.md)安装锁定依赖，运行：

```powershell
uv run --frozen python scripts/check_release.py
```

这个入口覆盖后端 lint/format/离线测试、API 类型一致性和前端测试/lint/typecheck/build。涉及数据库、历史、授权、发布或任务行为时补充相应隔离集成测试；报告实际失败、跳过和未选择范围。纯文档改动检查链接、差异与公开文件。公开 CI 不验证真实提供商质量或生产容量。

History/State 只帮助理解意图；回答的事实支持来自本轮授权文档 Evidence。测试应覆盖有效结果幂等、scope、事务发布、失效尝试、取消与 UNKNOWN，不通过弱化断言或修改历史记录使验证通过。

设计、实现与运行授权按[开发方法](docs/AI_DEVELOPMENT_PLAYBOOK.md)及[工程治理](docs/ENGINEERING_GOVERNANCE.md)执行；接受一个设计不自动授权后续付费运行。评测保留集合身份、来源、失败分母与独立审阅边界，合成样本和自动 Judge 不等于独立人工认证。

提交前检查完整差异、当前公开树与 Git 历史。排除 `.env`、`.runtime`、下载标准、数据库、模型、缓存、浏览器临时文件和作品集工作产物；README 图片须显式选择并保留第三方摘录归属。Docker 只操作明确属于本项目的隔离资源，禁止全局清理。

最新正式发布为 `v0.2.0`。`main` 上的后续改进为 Unreleased；不要因普通提交改写历史标签、Release 或制造新的版本号。