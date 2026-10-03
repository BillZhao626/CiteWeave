# 本地运行与复现

Merged runtime reliability and isolated-PG reproduction: [M1 evidence](V02B_RUNTIME_RELIABILITY_M1.md#reproduction-and-limits). Operator recovery uses `python scripts/reconcile_conversations.py --workspace <workspace-uuid> --limit 32`; it changes only expired durable bookkeeping and never dispatches a provider. Use isolated test databases for verification; default runtime policy remains unavailable and historical grants cannot be reused.

## 无模型离线检查

安装 Python 3.12、Node 22.20+、pnpm 11.19.0；在仓库根目录运行：

```powershell
python -m pip install uv==0.12.13
uv sync --frozen
pnpm --dir apps/web install --frozen-lockfile
uv run --frozen python scripts/check_release.py
```

该入口适用于 Windows / Linux 的源码检查，安装阶段需要访问公开依赖仓库。它不安装 models extra，不获取模型或语料，不需要 `.env`，不调用提供商。pytest 使用 `-m "not integration"`，明确排除需要 PostgreSQL / Redis / Qdrant / 模型的测试；前端覆盖类型、lint、Vitest、构建和 OpenAPI 类型一致性。

验证 Compose 语法（只解析，不启动、不输出环境变量值）：

```powershell
docker compose --env-file .env.example -f deploy/compose.m0.yml -f deploy/compose.m1.yml config --quiet
```

`.env.example` 只含占位符与安全默认值，不是可直接用于部署的凭据文件。完整启动脚本调用 `experiments/bootstrap.py` 为首次安装生成随机本地凭据，不覆盖已有 `.env`。

## 完整工作台：已验证的 Windows 环境

前提：Windows 11、PowerShell 7、Python 3.12、Node 22.20+、pnpm 11.19.0、Docker Desktop（Linux containers）及兼容 CUDA 12.6 的 NVIDIA 驱动。参考机器有 16 GB RAM / 8 GB VRAM。首次安装需要网络、模型与依赖磁盘空间；CPU-only 和 Linux 完整部署未验证。

```powershell
.\scripts\m1.ps1 -Setup
```

脚本安装锁定依赖和 E5 / BGE 模型，构建前端，启动本地模型 gateway、PostgreSQL、Redis、Qdrant、API 和 worker，并执行迁移。只对本项目命名资源操作。服务端口：工作台 18080、模型 gateway 18081、PostgreSQL 15432、Redis 16379、Qdrant 16333；主机映射仅监听 loopback。`host.docker.internal` 用于容器访问本机模型 gateway。

打开 [工作台](http://127.0.0.1:18080/)，从本机 `.env` 读取 `CW_ADMIN_TOKEN` 登录。不要把 token 发到 issue、日志或前端构建变量里。新安装是空知识库，先创建知识库，再上传 `apps/web/public/original-handbook.pdf`。等待 READY 后再查询。

真实生成需要在启动终端设置自己的 `DEEPSEEK_API_KEY`，随后执行：

```powershell
.\scripts\m1.ps1 -Action Up
```

该操作把配置传入本地服务；Key 不需要写入源码。真实 Ask 和模型评测可能计费，公开 CI 不执行它们。没有 Key 时没有真实生成服务；已有文档和 Run 的读取仍可用。此命令不创建会话运行授权，完整会话另见下文可用性边界。

停止与查看状态：

```powershell
.\scripts\m1.ps1 -Action Status
.\scripts\m1.ps1 -Action Stop
```

Stop 保留数据卷与原文。升级前同时备份 PostgreSQL 与 `.runtime/blobs`；不要删除卷来模拟升级。

## 公开语料与结构化查询

```powershell
uv run --frozen python scripts/fetch_public_telecom.py
```

脚本从官方来源获取固定版本并检查哈希，输出目录是 `.runtime/private/public-telecom`。若官方字节变化，先检查版本，不要关闭校验。来源与权利见 [CORPUS](CORPUS.md)。

创建独立知识库，通过 API 上传标准文档。普通 UI 上传保留原创手册的兼容默认；结构化文档必须显式选择参数：

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

`license=permission-held` 是调用者对持有适用使用许可的声明，须先核对 RFC 的 IETF Trust 条款或 MQTT 的 OASIS 条款；不是仓库对标准的通用再授权。结构化路径接受上限 32 MiB / 600 页；普通 UI 的兼容上传上限为 10 MiB。上传完成后等待 durable READY，在 Documents / Structure 检查章节、Parent / Child 和原文 span，再在 Ask 选择 `telecom-structural-v1` 查询路径。

截图所用结构化回答选择了 `answer-telecom-consistency-v1`。要显式选择同一 prompt，在本地 `.env` 增加下面的非秘密配置，再运行 Up：

```dotenv
CW_TELECOM_ANSWER_PROMPT=answer-telecom-consistency-v1
```

默认仍是 `answer-telecom-v1`。这个选择不改变旧 Run，也不保证新生成文字与截图相同。七份展示文档及既有记录不会从 Git 下载；需要使用者获取、上传并查询。

## 验证范围与版本

公开离线检查验证源码可安装、测试和构建，不代表本轮重新验证了 GPU 模型、真实生成、worker 故障、跨库比较或生产容量。真实集成测试须使用隔离数据库和本地服务；不要对已有演示数据库直接运行故障测试。

`v0.1.0` 是历史公开源码发布标签。当前 Python 包、frontend package 与 FastAPI/OpenAPI 均为 `0.2.0`，未来标签为 `v0.2.0`，尚未创建；版本元数据更新不改变 schema 字段或运行语义。历史证据文件名保持不变。

## 三层发布验证

- **Tier A**：Windows / Linux 离线源码门禁，锁定依赖安装需网络；不得借用 `.env`、旧 `.venv` / `node_modules`、`.runtime`、模型、数据库、私有语料或未跟踪文件。具体干净候选身份与执行结果见 [发布准备](V02_RELEASE_READINESS.md)。
- **Tier B**：Docker Compose 2.24.4+（使用 `!override` / `!reset`）和 Docker Linux containers，运行下方服务烟测。镜像构建/首次拉取可能需网络。脚本用唯一 project、全新卷、无 host port、内部 network 及随机临时凭据，不读取本地 `.env`；验证真实 PG/Redis/Qdrant、API 迁移和 readiness、静态应用/PDF.js/原创手册、空队列 worker ping 与关停。不会提交任务或访问模型/提供商。
- **Tier C**：上文完整 Windows / NVIDIA 工作台；公开 CI 不执行。没有验证 CPU-only/Linux 完整模型部署。本次不重跑模型或真实生成。

```powershell
uv run --frozen python scripts/smoke_release.py
```

烟测使用现有 Compose 与 app Dockerfile；前置须完成 Tier A 的前端 build。独立临时资源仅由该脚本清理，已有数据卷及停机的旧 RAGFlow 资源不动。

## 会话可用性与升级边界

`/health/ready` 表示数据库可访问且 API startup migration 已执行，不表示模型/Conversation runtime 已开放。v0.2 Ask 的真实会话执行需要服务器端准确的 `CW_CONVERSATION_RUNTIME_POLICY`、经 hash 校验的 tokenizer、有限调用/计量/CNY/绝对期限授权及本地 E5/BGE gateway；仅设置 DeepSeek Key 不开放默认会话。无 Key/授权可检查持久数据与 Trace，不能产生新真实回答。旧单轮 API 真实生成同样需要用户 Key 并计费。

API 启动执行 `alembic upgrade head`，当前唯一 head `0014`。首次初始化与重复迁移由 Tier B 新空库验证；已有应用数据升级/备份恢复仍未验证。历史迁移不可重写，升级前备份 PostgreSQL 和 blobs；不可用删卷模拟迁移成功。
