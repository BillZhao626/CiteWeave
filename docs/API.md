# 当前 API

FastAPI/Pydantic 定义请求、响应及错误，[生成 OpenAPI](../contracts/openapi.json)和前端[生成类型](../apps/web/src/generated/api.ts)是接口来源；本机 `/docs` 提供交互文档。元数据为 `0.2.0`，`main` 包含发布后的 Unreleased 改进。

使用本机 workspace Bearer token 或同源 HttpOnly session cookie。写请求使用 cookie 时必须同源；提供商凭据始终保留在服务器。所有业务读取按 workspace 和固定来源版本授权。

## Conversation / Turn / Run

| 操作 | 路由与语义 |
| --- | --- |
| 创建会话 | `POST /v1/conversations`；需要 `Idempotency-Key`，相同 key 恢复同一会话 |
| 读取会话 | `GET /v1/conversations/{conversation_id}`；已发布 head 与活动 Turn/Run 身份 |
| 提交 Turn | `POST /v1/conversations/{conversation_id}/turns`；需要稳定 `Idempotency-Key` 和准确 `expected_head` |
| 读取 Run | `GET /v1/conversations/{conversation_id}/runs/{run_id}`；持久状态、期限及可用的已接受结果 |
| 读取结果 | `GET /v1/conversations/{conversation_id}/runs/{run_id}/result`；无 Acceptance 时返回 409 |
| 读取 Trace | `GET /v1/conversations/{conversation_id}/runs/{run_id}/trace`；已记录的查询、使用来源、证据身份与安全阶段诊断 |
| 取消 Run | `POST /v1/conversations/{conversation_id}/runs/{run_id}/cancel`；通过持久状态和 fencing 阻止失效发布 |
| 事件快照 | `GET /v1/conversations/{conversation_id}/runs/{run_id}/events`；一次有限 SSE 快照，不是生成 token 流 |

Turn 请求包含 `question`、`scope: {kb_id, version_ids}` 和 `expected_head`；首次为 null，后续使用上次读到的 Acceptance head。选定的文档版本必须授权且可用，不能用文件名替代不可变版本身份。完整字段、约束与响应类型见 OpenAPI。

重复 key 不开启新执行。HTTP 202 表示持久 ADMITTED，尚未接受；成功提交后仍应读回 Run/result。结果为 `documentary_answer`、`clarification` 或 `evidence_insufficient`。已接受的澄清或证据不足同样有 Acceptance，但不是有文献支持的事实回答。

默认 runtime 返回 `conversation_runtime_unavailable`；仅有提供商 Key 不开放会话。需服务器端精确请求 policy、有限 calls/token/CNY/期限授权与校验过的 tokenizer，配置边界见[快速开始](QUICKSTART.md)。结果不确定时不从客户端异常推断失败或自动换 key 重派；保留身份并读取持久状态。

## 只读检查

| 页面数据 | 路由 |
| --- | --- |
| Run 列表 | `GET /v1/runtime/conversation-runs?limit=25&offset=0` |
| 发布与可靠性 | `GET /v1/conversations/{conversation_id}/runs/{run_id}/inspection` |
| 上下文与解析观察 | `GET /v1/conversations/{conversation_id}/runs/{run_id}/context` |
| 本地服务观察 | `GET /v1/runtime/operations` |

Run 列表有界且按时间排序；不是跨会话的一笔事务快照。Publication 显示实际 Acceptance、State 摘要、当前 head 和它与该 Acceptance 的关系，后续 head 前进不会修改旧结果。

Context 的持久查询、使用来源及 Current Evidence 与可选输入观察分开。细节在本地观察记录与持久 provider phase 的请求／响应哈希、当前请求／scope／head、各源 Acceptance 和解释指纹一致时返回。三种可用性为：

- `VERIFIED_LOCAL_RECEIPT`：本地观察已通过身份与哈希核对。
- `NOT_RECORDED`：没有该观察，相关集合为 null。
- `UNVERIFIABLE`：观察存在但不能核对，相关集合为 null。

未记录不等于空输入，也不重构全部 Recent History 为 Relevant History。候选分支与近期归属是本地观察，并非独立的持久证明。Working State 只返回实际投影。该接口不返回原始 provider body、prompt、旧答案、秘密或虚构数值权重；结构一致性不证明模型相关性判断正确。

Operations 读取 PostgreSQL 状态，并执行有限 Redis/Celery/Qdrant/本地模型健康观察；不提交任务、不推理、不调用 LLM provider。配置了 Key 只表示配置存在，不能作为提供商健康证明。以上接口均不授予运行、恢复或重派权限。

## 文档、证据与兼容接口

摄取和结构化查询示例见[快速开始](QUICKSTART.md#公开技术语料)。`POST /v1/queries` 的兼容单轮 SSE delta 是草稿，只有校验后的 final 是最终结果；HTTP 200 流也可能以 error 结束。

Citation 解析的是该 Run 已授权的不可变来源版本与精确原文 span，Evidence 与 PDF 读取不能绕过 workspace/版本检查。旧查询／评测接口保留原 profile 身份，其示例与历史默认值见[兼容查询与评测 API](M3_API_USAGE.md)；这些接口存在不代表新评测运行已有授权。

## 生成与核对类型

修改 Pydantic schema 后，在仓库根目录运行：

```powershell
uv run --frozen python scripts/export_openapi.py
pnpm --dir apps/web generate:api
uv run --frozen python scripts/check_contracts.py
```

导出工具更新两份 OpenAPI；生成工具更新 frontend TypeScript。check 会与当前 schema 核对并在临时目录重新生成，不静默修复过期文件。
