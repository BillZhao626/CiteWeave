"""M0 fault-injection worker. The test payload is never exposed by a public API."""

import os
import time
from uuid import uuid4

from celery import Celery

from citeweave import jobs

app = Celery("citeweave", broker=os.environ.get("CW_BROKER_URL", "redis://127.0.0.1:16379/0"))
app.conf.update(
    task_default_queue="citeweave-m0",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_timeout=2,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "visibility_timeout": int(os.getenv("CW_VISIBILITY_TIMEOUT", "120")),
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
        "retry_policy": {"max_retries": 0},
    },
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
)
OWNER = str(uuid4())


@app.task(name="citeweave.execute", acks_late=True)
def execute(identity):
    job = jobs.claim(identity, OWNER)
    if job is None:
        return
    # Only the first attempt pauses before commit, allowing deterministic crash/recovery checks.
    pause = job["payload"].get("pause_before", 0) if job["attempts"] == 1 else 0
    for _ in range(pause):
        time.sleep(1)
        if not jobs.heartbeat(identity, job["fence"]):
            return
    committed = jobs.complete(identity, job["fence"], {"value": job["payload"].get("value", "ok")})
    if committed:
        time.sleep(job["payload"].get("pause_after", 0))
