# M1 API 使用

运行后访问 `http://127.0.0.1:18080/docs`。业务接口使用个人 Bearer token，或工作台的 HttpOnly cookie。cookie 写操作须同源 Origin；token 不放 URL。

```python
from uuid import uuid4
import httpx
from citeweave.settings import settings, ROOT

client = httpx.Client(base_url="http://127.0.0.1:18080", trust_env=False, timeout=60,
    headers={"Authorization": "Bearer " + settings().admin_token.get_secret_value()})
kb = client.post("/v1/knowledge-bases", json={"name": "原创观测站"},
    headers={"Idempotency-Key": str(uuid4())})
kb.raise_for_status()
kb_id = kb.json()["id"]
upload = client.post(f"/v1/knowledge-bases/{kb_id}/documents",
    params={"filename": "original-handbook.pdf", "license": "original"},
    headers={"Idempotency-Key": str(uuid4()), "Content-Type": "application/pdf"},
    content=(ROOT / "apps/web/public/original-handbook.pdf").read_bytes())
upload.raise_for_status()  # 202：这里只写原件、版本、任务、outbox
job_id = upload.json()["job"]["id"]
job = client.get(f"/v1/jobs/{job_id}")
job.raise_for_status()
print(job.json()["status"])  # 等到 READY 再发起回答
```

重传时添加 document_id query 参数并使用新 key。相同 key / 相同载荷重放，载荷冲突返回 409。许可声明可用 original、CC0-1.0、CC-BY-4.0、permission-held；系统不认证授权真实性。

```python
# 此步会调用已配置的 DeepSeek 并产生费用。
with client.stream("POST", "/v1/queries",
    headers={"Idempotency-Key": str(uuid4())},
    json={"kb_id": kb_id, "question": "湖畔观测站的温度多久采样一次？"},
) as response:
    response.raise_for_status()
    for line in response.iter_lines():
        if line.startswith("data: "):
            print(line)  # stage → provisional delta → final 或 error
```

客户端须等 final 确认答案。delta.provisional=true 不能作为最终结论；error、断流或缺少 final 时撤回。已完成 run 用相同 key / 问题重放 final，不再次生成；进行中返回 409。

| 操作 | 接口 |
|---|---|
| 知识库列表 / 详情 | GET /v1/knowledge-bases、/v1/knowledge-bases/{id} |
| 文档列表 / 版本和任务 | GET /v1/knowledge-bases/{id}/documents、/v1/documents/{id} |
| 任务历史 | GET /v1/jobs/{id} |
| 答案与候选 trace | GET /v1/runs/{id} |
| 引用定位 | GET /v1/evidence/{evidence_id}?run_id={run_id} |
| 不可变原件 | GET /v1/document-versions/{id}/content |

span.boxes[].page_index 从 0 开始，显示页码加 1；坐标归一化到显示后的页面。Unicode offset 是 codepoint offset，不是 JS UTF-16 下标。引用须属于指定 run 及授权范围。

HTTP 错误格式 `{error:{code,message,retryable},request_id}`；流开始后用 type:error。典型错误：401 unauthorized、404 作用域外对象、409 idempotency_conflict / no_ready_documents / query_running、413 文件过大、422 参数限制、429 single_query_capacity / monthly_budget_reserved、503 database_unavailable。invalid_or_missing_citation 不发布假成功。

usage 保存 token、provider model/id、费率卡和 uncertain_retry；estimated_yuan 可空，actual_cost 固定 unavailable。当前费率卡仅支持 deepseek-flash；更换模型应同步修改适配器、费率卡和测试。
