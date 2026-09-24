# 本地运行与复现

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

该操作把配置传入本地服务；Key 不需要写入源码。真实 Ask 和模型评测可能计费，公开 CI 不执行它们。没有 Key 时没有真实生成服务；已有文档和 Run 的读取仍可用。

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
  &license=IETF-Trust
  &ingestion_profile=telecom-protocol-pdf-v1
Content-Type: application/pdf
Authorization: Bearer <your-local-admin-token>
Idempotency-Key: <a-new-unique-key-for-this-upload>
Body: official PDF bytes
```

示例中的 `IETF-Trust` 是来源许可说明，不是通用重新授权；MQTT 请使用其 OASIS 来源说明。结构化路径接受上限 32 MiB / 600 页；普通 UI 的兼容上传上限为 10 MiB。上传完成后等待 durable READY，在 Documents / Structure 检查章节、Parent / Child 和原文 span，再在 Ask 选择 `telecom-structural-v1` 查询路径。

截图所用结构化回答选择了 `answer-telecom-consistency-v1`。要显式选择同一 prompt，在本地 `.env` 增加下面的非秘密配置，再运行 Up：

```dotenv
CW_TELECOM_ANSWER_PROMPT=answer-telecom-consistency-v1
```

默认仍是 `answer-telecom-v1`。这个选择不改变旧 Run，也不保证新生成文字与截图相同。七份展示文档及既有记录不会从 Git 下载；需要使用者获取、上传并查询。

## 验证范围与版本

公开离线检查验证源码可安装、测试和构建，不代表本轮重新验证了 GPU 模型、真实生成、worker 故障、跨库比较或生产容量。真实集成测试须使用隔离数据库和本地服务；不要对已有演示数据库直接运行故障测试。

`v0.1.0` 是首次公开源码发布标签。API / 包内保留已有 `0.3.0-alpha.1` / `0.3.0a1` 工程版本，以避免改变冻结接口契约；二者不是质量评级。历史脚本与 ADR 的阶段名称仅作技术兼容。
