# M2 本地运行与恢复指南

## 安装、启动与开发

保留已验证的 [M1 安装流程](M1_LOCAL_DEVELOPMENT.md)。入口名称 `scripts/m1.ps1` 与 Compose 项目名 `citeweave-m0` 为保护已有卷而保留，运行内容已经是 M2；不是启动旧实验 worker。

```powershell
.\scripts\m1.ps1 -Setup        # 首次安装锁文件依赖和固定 revision 模型
.\scripts\m1.ps1 -Action Up    # 日常构建并启动
.\scripts\m1.ps1 -Action Status
.\scripts\m1.ps1 -Action Stop  # 保留卷与文件
.\scripts\m1.ps1 -Action Verify
```

Web/API `127.0.0.1:18080`，模型 `18081`，PG `15432`，Valkey `16379`，Qdrant `16333`。Vite `15173` 为开发时可选入口；最终验收使用构建后的 `18080`。模型代码变化后先 Stop 再 Up，避免已有健康模型进程继续使用旧代码。仅业务镜像 / 前端变化可直接 Up。

管理员 / 数据库凭据由本机 bootstrap 生成。个人 DeepSeek key 由环境配置，不输出到 shell history、聊天、前端或 trace。`.env.example` 列出 query deadline、provider/model attempts、backoff 和 breaker 参数；Compose 同步传给 API 与 worker。修改后 Up 使配置生效；进行中的评测检测配置漂移并明确失败，不混算。

## 评测

先运行 `python scripts/fetch_eval_corpus.py`（使用项目 .venv）获取并验证三份 manifest 原件。若远端文件变化导致 hash 不同，停止使用，不覆盖冻结数据集。按各来源的使用条件将原件上传同一知识库并等待 READY；不会把公开可下载误作重新分发许可。

页面“评测”或 `scripts/evaluate.py --kb <id> --split dev|test|all` 创建任务。中断只用 `--resume <id>`，保留原 eval identity。机器工件和 Markdown 输出至 `.runtime/evaluation/runs/<id>/`，受忽略保护。冻结比较与指标分母见 [评测方法](M2_EVALUATION.md)。

## 故障排查与安全维护

1. 回答问题从 Run Inspector 查看出错阶段、error category、每次调用、usage 与物理版本范围；失败或断流不能把草稿作为 final。
2. 摄取问题从 Job 看 status / attempt / fence 事件。周期恢复扫描自动接管过期任务，不手改 READY，不依赖 Valkey 是否还持有原消息。
3. breaker open 时先查上游健康和冷却期限；半开只允许一个探测。不要循环强行重试绕过 breaker。
4. Versions 页重建当前或历史 READY 版本；接收操作后在 System/Jobs 查看最终 Job。重建校验失败时保留原发布索引。
5. 回滚显式选择历史版本，expected active 检测竞争。历史 citation 不切换到新版本。若有新版本正在摄取，应等待其终止再回滚。
6. GC 先预览保护原因，再对单个明确候选执行删除；操作记录通过 `/v1/operations` 查询。未知 collection 即使名字像 CiteWeave，也不能推定可删。不会自动删除历史引用、原文或 Blob。

推荐继续保持单 Query、worker concurrency=1、一个 GPU 推理槽。短时并发实验不是持续服务容量承诺。不要同时运行大型训练、另一套 RAGFlow 和批量评测抢占本机资源。

## 备份与隔离恢复

```powershell
# 确认本项目没有正在摄取/回答/评测；脚本也会检查。
.\.venv\Scripts\python.exe scripts/backup_restore.py
```

脚本只短暂停止本项目 API/worker，检查没有未完成业务后 `pg_dump -Fc` 并复制全部不可变 CAS，记录 hash / 文件数 / Run / citation 数。备份落在 `.runtime/backups/<UUID>/`；生产服务随即恢复。

演练创建 UUID 数据库 `cw_restore_<UUID>`、独立 blob 目录和临时 Qdrant（本机 16334）。从 dump 恢复 PG，以空 Qdrant 重建所有 READY version；每条历史 citation 重新解析原 PDF 验证。结束后只清理脚本创建的测试 DB/容器；备份文件保留。不会覆盖生产数据库或操作旧 RAGFlow。

实际首次演练：8 个版本、30 个 CAS 文件、51 个 Run、23 条 citation，85.11 秒，通过结果在 `reports/m2-recovery.json`。这是本机隔离恢复演练，不等于异地容灾或硬件损坏后的 RTO 保证。

离机保存时应把整个备份目录安全复制到个人受控介质，并验证 manifest / dump hash。不要把 dump 或 `.runtime/` 加入 Git。M2 未提供在线 PITR、自动加密和远程恢复。数据库 schema 降级不是产品“版本回滚”；产生 M2 事实后，恢复旧应用必须使用匹配版本的完整备份，不能直接跑 0003 downgrade 删除治理表。

## 复现验收

`scripts/verify.py` 默认输出 m2 门禁，创建并清理独立测试数据库；使用真实 PG/Qdrant/E5/BGE 和模拟 LLM。`scripts/fault_acceptance.py --milestone m2` 在没有其他摄取时执行三次真实 worker SIGKILL，finally 关闭注入。`scripts/m2_load.py` 只调用本地模型网关，不产生 LLM 费用。不要并行运行这些依赖同一 GPU 的实验后把数字当独立负载结果。

## 本机 Docker socket 故障记录

2026-09-15 Docker Desktop 4.55 启动报 `engine.sock` / `dockerInference` 无法访问。根据本机日志以及 Docker 官方仓库的同类 [issue 536](https://github.com/docker/desktop-feedback/issues/536)、[issue 554](https://github.com/docker/desktop-feedback/issues/554)，停止已崩溃的 Docker 程序后，将仅含运行 socket 的对应父目录改名保留，再启动使其重建。属于基于同类故障报告的可逆处理，不是维护者保证的修复。

13:35 保留 `AppData/Local/docker-secrets-engine.citeweave-stale-20260915` 和 `Docker/run.citeweave-stale-20260915`。22:33 重新启动时同类 dockerInference 错误复发，再保留 `Docker/run.citeweave-stale-20260915-2234`。没有 factory reset、prune、删除卷或 WSL unregister。先诊断当前日志再处理，不把该方法做成无条件自动清理。
