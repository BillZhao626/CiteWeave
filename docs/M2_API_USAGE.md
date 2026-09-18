# M2 API 使用

所有接口使用现有 Bearer token，或同源 HttpOnly cookie；所有列表和详情按 workspace 授权。API key 不给前端，不放 URL。核心上传与 SSE 使用方式继承 [M1 API](M1_API_USAGE.md)。运行中的 `/docs`、[OpenAPI](../contracts/openapi.json) 是完整字段和约束的事实来源，前端类型由其生成。

| 能力 | 接口与关键参数 |
|---|---|
| 回答记录 | GET `/v1/runs?kb_id=...&limit=25&offset=0`；GET `/v1/runs/{id}` 查看快照、candidates、stages、calls、usage、estimated_yuan |
| 后台任务 | GET `/v1/jobs?limit=25&offset=0`，GET `/v1/jobs/{id}` 查看 kind、attempt、事件与错误 |
| 文档版本 | GET `/v1/documents/{id}/versions?limit=25&offset=0`，包括 active_version_id |
| 重建 | POST `/v1/document-versions/{id}/rebuild`，带 Idempotency-Key；202 返回 Operation，关联 job_id |
| 回滚 | POST `/v1/documents/{id}/rollback`，body 为 target_version_id 和 expected_active_version_id；带 Idempotency-Key |
| 清理预览 | GET `/v1/indexes/gc?limit=50&offset=0`，逐项 candidate/protected/reasons |
| 清理执行 | POST `/v1/indexes/gc`，body 为 name，带 Idempotency-Key；每次只操作一个已登记索引 |
| 维护审计 | GET `/v1/operations?limit=25&offset=0` |
| 冻结数据集 | GET `/v1/evaluation-datasets`，包括 source / hash / 许可说明 |
| 批量评测 | POST `/v1/evaluations`，body 为 kb_id、dataset_id、split（dev/test/all），带 Idempotency-Key |
| 评测记录 | GET `/v1/evaluations?limit=25&offset=0`，GET `/v1/evaluations/{id}` |
| 逐题记录 | GET `/v1/evaluations/{id}/cases?limit=25&offset=0` |
| 导出 | GET `/v1/evaluations/{id}/artifact` 返回完整 JSON；`.../report` 返回 Markdown |
| 停止后续题目 | POST `/v1/evaluations/{id}/cancel`，天然幂等；当前题目在既定 deadline 内结束 |
| 人工复核 | POST `/v1/evaluations/{id}/cases/{case_id}/review`，body 为 verdict、reason；操作者必须是真实人工复核者 |
| 系统状态 | GET `/v1/system`，模型队列、breaker、job 计数、累计估算 / 未知预留；actual_charge=unavailable |

列表 limit 为 1–100，offset ≥0。数据集固定 48 题，因此完整 artifact 采用一次导出，其余逐题浏览分页。可变诊断内容通过 JSON 字段表达；业务命令与返回对象使用明确 Pydantic schema。

```powershell
# 已准备三份 manifest 原件并完成摄取的 KB；命令只输出 ID 和进度，不打印 token。
.\.venv\Scripts\python.exe scripts/evaluate.py --kb <KB_UUID> --split dev
# 终端中断后按原 ID 继续等待/导出，不创建第二次付费运行。
.\.venv\Scripts\python.exe scripts/evaluate.py --resume <EVAL_UUID>
```

HTTP 错误仍为 `{error:{code,message,retryable},request_id}`。作用域外对象 404；相同幂等键不同请求、回滚竞争、缺失或重复 corpus、正在运行的评测容量为 409；分页/输入错误为 422；预算和单 Query 容量为 429。SSE 开始后失败通过 `type:error`，不得把 HTTP 200 当成有效 final。

`estimated_yuan=null` 表示至少有一次调用费用未知，继续保留预算预留。逐次 calls 保留已知 input/output 分项和失败 / 重试；已知部分不等于全请求最终账单。固定费率卡和账户外调用的限制见 [M2 限制](M2_LIMITATIONS.md)。
