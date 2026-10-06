# 本地运行与复现

本页对应 `main` 的当前源码。最新正式发布为 `v0.2.0`；后续改进为 Unreleased，Python、frontend 与 FastAPI/OpenAPI 元数据仍为 `0.2.0`。

## 安装依赖与离线检查

准备 Python 3.12、Node 22.20+、pnpm 11.19.0。在仓库根目录运行：

```powershell
python -m pip install uv==0.12.13
uv sync --frozen
pnpm --dir apps/web install --frozen-lockfile
uv run --frozen python scripts/check_release.py
```

依赖安装需要访问公开仓库。检查入口清空提供商 Key 与运行配置，启用离线模型标志，执行后端 Ruff lint/format、`pytest -m "not integration"`、PDF.js 资产与 notices、生成 OpenAPI/TypeScript 一致性、前端 typecheck/lint/Vitest/build 和文档链接检查。它不下载模型或语料，不需要 `.env`，不运行真实服务或提供商。

单独验证前端或后端时，可使用实际入口：

```powershell
pnpm --dir apps/web test
pnpm --dir apps/web lint
pnpm --dir apps/web typecheck
pnpm --dir apps/web build
uv run --frozen python -m pytest -q -ra -m "not integration"
uv run --frozen python scripts/check_contracts.py
```

## 隔离的真实服务烟测

需要 Docker Linux containers 与 Compose 2.24.4+。先完成上述前端构建，再运行：

```powershell
uv run --frozen python scripts/smoke_release.py
```

脚本使用现有 Dockerfile/Compose、新建临时项目和卷、随机临时凭据及内部网络；验证 PostgreSQL/Redis/Qdrant、迁移、API readiness、静态应用/PDF.js/原创手册和空队列 worker。它不读取本机 `.env`，不提交摄取或生成任务，不连接模型／提供商；结束后仅清理自身的隔离资源。首次镜像构建或拉取可能需要网络。

只检查 Compose 语法而不启动服务：

```powershell
docker compose --env-file .env.example -f deploy/compose.m0.yml -f deploy/compose.m1.yml config --quiet
```

`.env.example` 是占位符与安全默认值，不是部署凭据。不要运行会输出完整解析配置的命令分享凭据。

## 完整工作台：已验证的 Windows 环境

前提：Windows 11、PowerShell 7、Python 3.12、Node 22.20+、pnpm 11.19.0、Docker Desktop（Linux containers）及兼容 CUDA 12.6 的 NVIDIA 驱动。参考机器为 16 GB RAM / 8 GB VRAM。首次安装需要网络及模型/依赖磁盘空间；完整 CPU-only 或 Linux 模型部署尚未验证。

```powershell
.\scripts\m1.ps1 -Setup
```

该脚本安装锁定依赖和 E5/BGE 模型，构建前端，启动本地模型 gateway、PostgreSQL、Redis、Qdrant、API 和 worker，并执行迁移。`experiments/bootstrap.py` 为首次安装生成随机本地配置，不覆盖已有 `.env`。

| 服务 | 本机 loopback 端口 |
| --- | --- |
| 工作台 / API | 18080 |
| 本地模型 gateway | 18081 |
| PostgreSQL | 15432 |
| Redis | 16379 |
| Qdrant | 16333 |

打开[工作台](http://127.0.0.1:18080/)，使用本机 `.env` 的 `CW_ADMIN_TOKEN` 登录。不要把 token 发送到 issue、日志或前端构建变量。新安装是空知识库；创建知识库、上传 `apps/web/public/original-handbook.pdf`，等待 READY 后可检查文档、结构和原文。

真实生成使用自己的 `DEEPSEEK_API_KEY`，在启动终端配置后执行：

```powershell
.\scripts\m1.ps1 -Action Up
```

该命令把本地配置传入服务，但不创建 Conversation 执行授权。真实生成和模型评测可能计费；公开 CI 不执行它们。没有 Key 时可读取已有文档和 Run，但无法获得新的真实生成答案。

状态与停止：

```powershell
.\scripts\m1.ps1 -Action Status
.\scripts\m1.ps1 -Action Stop
```

Stop 保留数据卷和原文。升级前同时备份 PostgreSQL 与 `.runtime/blobs`；不要删除卷模拟升级成功。

## 公开技术语料

```powershell
uv run --frozen python scripts/fetch_public_telecom.py
```

脚本从官方来源获取固定版本并检查哈希，保存到忽略目录 `.runtime/private/public-telecom`。官方字节变化时先检查版本，不关闭校验。来源、归属与使用条款见[语料](CORPUS.md)和[数据声明](DATA_NOTICES.md)；原始标准与图片中的历史记录不随 Git 下载。

结构化标准上传需要显式参数，API 示例为：

```text
POST /v1/knowledge-bases/{kb_id}/documents
  ?filename=rfc9114.pdf
  &license=permission-held
  &ingestion_profile=telecom-protocol-pdf-v1
Content-Type: application/pdf
Authorization: Bearer <your-local-admin-token>
Idempotency-Key: <a-new-unique-key-for-this-upload>
Body: official PDF bytes
```

`license=permission-held` 是调用者持有适用许可的声明，须先核对 RFC 的 IETF Trust 或 MQTT 的 OASIS 条款。结构化路径上限为 32 MiB / 600 页；普通 UI 兼容上传上限为 10 MiB。等待持久 READY，再在 Documents/Structure 检查章节、Parent/Child 和原文 span；结构化查询使用 `telecom-structural-v1`。

产品图片中的回答使用 `answer-telecom-consistency-v1`。显式选择相同 prompt 时，可在本机 `.env` 配置以下非秘密字段并执行 Up：

```dotenv
CW_TELECOM_ANSWER_PROMPT=answer-telecom-consistency-v1
```

默认仍为 `answer-telecom-v1`。该设置不改变旧 Run，也不保证生成文字与图片相同。

## 会话执行与检查页面

`/health/ready` 只表示数据库可读且 API 启动迁移已执行，不表示模型或 Conversation runtime 已开放。

当前多轮执行要求服务器端 `CW_CONVERSATION_RUNTIME_POLICY` 精确绑定 workspace/Conversation/请求、绝对期限及有限 calls/input/output/CNY；`CW_CONVERSATION_TOKENIZER` 指向 hash 校验的官方离线 tokenizer，并需本地 E5/BGE gateway 与提供商 Key。没有通用默认授权或公开 grant API；仅设置 Key 不会开放会话。policy 结构由 [RuntimePolicy](../src/citeweave/conversation_runtime.py) 定义，旧授权不可复用。

已有记录的 Ask、Run/Trace、Publication 和 Context 检查不调用生成提供商。Context 的候选与引用解析细节依赖可选本地观察记录；缺失或核对失败显示明确可用性状态，持久查询与当前 Evidence 仍单独读取。Operations 仅执行有界服务探测。路由与读取契约见[API](API.md)。

## PostgreSQL 回归与恢复

涉及历史选择、发布、授权、取消或并发锁的修改，在本机 PostgreSQL 管理员配置下运行隔离集成测试；测试创建/删除自身 UUID 命名数据库，不直接迁移已有应用数据库。必须先确认配置指向 loopback PostgreSQL。

```powershell
$env:CW_RUN_INTEGRATION = "1"
uv run --frozen python -m pytest -q tests/test_conversation_postgres.py tests/test_conversation_runtime_postgres.py tests/test_context_inspection_postgres.py tests/test_runtime_reliability_postgres.py
```

数据库凭据由本机环境／配置提供，不写进命令、仓库或报告。上述测试使用合成数据和受控提供商传输，不能证明真实模型质量。其余受影响集成模块与完整方法见[可靠性](V02B_RUNTIME_RELIABILITY_M1.md)、[可观察性](V02B_OPERATIONAL_OBSERVABILITY_M2.md)及[并发测量](V02B_CONCURRENCY_PERFORMANCE_M3.md)。

只读恢复检查：

```powershell
uv run --frozen python scripts/reconcile_conversations.py --workspace <workspace-uuid> --limit 32 --inspect
```

去掉 `--inspect` 会显式执行过期持久状态 reconciliation，须由操作者决定；不会自动调用提供商或重派 UNKNOWN。

API 启动执行 `alembic upgrade head`，当前唯一 head 为 `0014`。首次初始化与重复迁移由隔离烟测验证；历史迁移不重写，已有生产数据升级／备份恢复尚无完整验证。回归、恢复测试和物理引用校验不构成生产 SLO 或通用语义质量认证。