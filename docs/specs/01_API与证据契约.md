# S-01 API 与证据契约

> M0 已执行：已验证不变量以 [M0 冻结范围](00_M0冻结范围.md) 为准，本文其余部分仍是完整目标设计。实测结果见 [M0 报告](../05_M0实测与选型结论.md)。

状态：完整产品目标设计；已冻结子集见 M0 冻结范围。本文未实施接口的限额仍为拟议初值。需求编号用于测试与 issue 追踪。

## 身份与资源约束

所有主键为服务端产生的 UUID；所有资源属于 workspace。开发环境也用个人管理员密钥或会话，匿名 demo 仅访问明确公开且已审核的数据。owner/principal 来自认证结果，不能由请求 body 指定。角色初期为 owner/editor/viewer。缺认证 401；已认证但无操作权限 403；无权读取的对象可统一返回 404 以减少枚举。

Token 只在后端读取；前端不保存 DeepSeek key。浏览器会话采用 HttpOnly/Secure Cookie 与 CSRF 保护，API 客户端可用有限 scope token，数据库保存 token hash。M0 先定一种主路径，避免一次实现多套身份提供商。

## 资源接口

| 方法与路径 | 请求要点 | 成功响应/行为 |
|---|---|---|
| POST /v1/knowledge-bases | name、description、profile_id；Idempotency-Key | 201 KB，默认 draft |
| GET /v1/knowledge-bases | cursor、limit≤100 | 当前 principal 可见列表 |
| POST /v1/knowledge-bases/{id}/documents | multipart 文件、metadata、来源许可声明 | 202 document_revision + ingestion_job_id |
| GET /v1/jobs/{id} | 已授权 job | 状态、阶段、进度、attempt、错误码 |
| POST /v1/jobs/{id}/cancel | 取消理由 | 202 cancel_requested，实际退出后 cancelled |
| POST /v1/knowledge-bases/{id}/builds | 文档版本清单、index profile | 202 snapshot/job，旧 active 不变 |
| POST /v1/knowledge-bases/{id}/releases | ready snapshot、prompt/policy、expected_revision | 201 release；事务切换 active |
| POST /v1/knowledge-bases/{id}/rollback | target_release_id、expected_revision | 200 新发布事件，旧 immutable release 不被修改 |
| DELETE /v1/knowledge-bases/{id} | 幂等键 | 202 清理任务；立即进入 tombstoned 不可查询 |
| POST /v1/queries | question、kb_ids、可选 release_ids、history、debug | 200 完整 QueryResult，或预协商事件流 |
| GET /v1/runs/{id} | scope: runs:read | 用户可见答案与阶段摘要；debug 需额外授权 |
| GET /v1/evidence/{id} | run_id 与引用范围 | 精确版本、原文片段、定位描述 |
| GET /v1/document-revisions/{id}/content | 已授权原件 | 安全 Content-Type/Disposition，支持 PDF 读取 |
| POST /v1/evaluations | dataset_revision、候选 release、协议、预算上限 | 202 eval_job_id |
| GET /v1/evaluations/{id} | 已授权 eval | 状态、完整分母、切片指标、失败项 |
| GET /health/live 与 /health/ready | 公开仅最小状态 | 进程存活/必要依赖可用；内部错误不暴露地址或凭据 |

上传初值 20 MB/文件、500 页/文档；M0 根据解析实测调整。校验 MIME、文件签名、解压比例、总大小、页数与解析时限。默认不接收任意 URL，也不接入压缩包递归解析。若后续支持 URL，要限制 scheme、DNS/重定向目标、下载大小、超时与私网地址。HTML/Markdown 渲染禁用原始脚本、自动远程资源加载。

## 查询边界

question 最长 8000 字符；history 最多 8 轮并独立 token 限额；kb_ids 1–5；top_k 默认 8、最大 20；总 context token 上限初值 6000。用户不能传任意 provider URL、文件路径或自定义 Python 插件。

kb_ids 必须显式提供；未知 KB、未 ready、无授权必须明确失败，不自动换到默认库。跨库查询一次解析固定 release 映射，不能只对主 dense 通道过滤。

HTTP 错误统一 envelope：error.code、error.message、error.retryable、request_id、可选 retry_after_ms。422 参数错误、409 revision/idempotency 冲突或 KB 未 ready、413 超限、429 并发/速率/预算限制、502 provider 无效响应、503 必要依赖不可用、504 deadline。详细堆栈只进内部脱敏日志。

证据不足是领域结果，返回 200 + answer_status=insufficient_evidence；供应商超时不是“证据不足”。降级回答 200 + degraded=true + degradation_reasons；失败不能以 mock answer 伪装成功。

## QueryResult

必需字段：run_id、request_id、answer_status（answered/partial/insufficient_evidence）、answer、claims、citations、release_map、degraded、degradation_reasons、timings_ms、usage、created_at。debug 条件返回候选轨迹对象键；不能把未过滤 raw payload 全量回给浏览器。

Claim：claim_id、text、citations（evidence_span_id 列表）、support_status（assessed_supported/insufficient/conflicting/not_assessed）、verification_method、verifier_revision。没有证据的解释必须明确为不足或推断，不能把推断混入经证据支持的事实。

Citation 不是模型自由生成的 URL，它是服务端根据本 run 可用证据 ID 解析的结构对象。模型最多引用当前上下文中的临时编号；临时编号映射保存在 run 中，用户点击后解析稳定 evidence_span_id。

## 精确证据模型

| 字段 | 约定 |
|---|---|
| evidence_span_id | 不可变稳定 ID，关联 workspace/KB/document_revision；不能由显示序号充当 |
| document_revision_id / source_sha256 | 必须绑定实际原件版本 |
| canonical_text_sha256 / normalizer_revision | 坐标依赖的规范文本和归一化算法版本 |
| block_id / chunk_id / parent_id | 块、检索片段和上下文父级关系 |
| start_offset / end_offset | 规范块文本中零基 Unicode code point 半开区间 [start,end) |
| quote / quote_sha256 | 必须等于该区间的原文，服务端重算；模型意译不是 quote |
| page_index / page_label | PDF 物理页零基索引，与印刷页码分开；UI 展示可为 index+1 |
| boxes | 可跨页多个矩形；左上为原点，归一化到 [0,1]，保存旋转/裁剪转换信息 |
| locator_kind | pdf_bbox / paragraph / table_cells；无 bbox 不能自动补零假定位 |
| table_location | 表、行/列、合并单元格、表头关系；不能将孤立数值脱离表头作为证据 |
| source_url / title / publisher / source_status | 来源与版本地位；仅作为证据属性，不自动作为主张归属 |
| locator_valid / quote_exact / support_status | 定位、文本一致性、语义支持分别记录 |

浏览器 JavaScript string offset 是 UTF-16，不能直接拿 Python code point offset 做 substring；由后端返回 quote 和块定位，必要时前端显式转换。原始 PDF 文本提取、OCR 纠错与规范文本不同；保存转换映射，定位失败降级为段落/页级且明确告知。

## 引用与流式输出

首版优先返回已验证的完整答案。需要流式体验时先推 stage、evidence_ready、heartbeat，验证后的 claim 再逐条提交；最后 answer_final、usage、done。若保留模型 token 预览，必须标记 unverified draft，校验后替换或撤回，不能让假引用先以验证状态出现。

采用 fetch 读取 POST 响应事件流；不把带凭据/查询正文放 EventSource URL。断线可凭 run_id 读取最终状态，重连不重新付费生成。客户端 AbortSignal 与服务 deadline 共同取消后续工作；已发出不可撤销的上游请求如实记录。开始流后错误使用 terminal error event，不伪造第二个 HTTP 状态。

## 开发者模式

显示 query 规范化、dense/sparse 候选/排名、RRF 贡献、rerank 分数、去重/筛选原因、上下文预算、引用绑定/验证、耗时、tokens、成本与 fallback。复盘的是可记录的外部链路与结构化结果，不收集或展示模型隐藏思维链。

普通用户默认看最小来源信息；完整 Prompt/上下文/文档片段与 trace 单独授权、设置保留期，公开分享前脱敏并确认数据许可。运行记录中的对象仍受实时撤权/删除影响。

## 契约验收

- A01：三个入口（API、UI、未来 MCP）同请求得到同一核心 schema，缺 KB 不换库。
- A02：跨 workspace/KB/run/document/eval 的所有读写及缓存命中均不得越权。
- E01：连续重复段落、中文/emoji、OCR 和表格的 quote/坐标有明确身份，定位失败不伪装通过。
- E02：文档更新/回滚期间旧 run 的引用保持原版本，撤权后不能读取旧引用。
- E03：模型生成不存在的 citation ID/offset/quote 被拒绝；最终答案无未知引用。
- A03：所有错误有稳定错误码和 request_id；任务失败和证据不足可区分。
- U01：Playwright 完成上传→问答→点击证据→回到答案；覆盖未完成/失败/取消和键盘访问。
