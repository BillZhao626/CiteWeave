from celery import Celery

from citeweave.settings import settings

app = Celery("citeweave-m1", broker=settings().broker_url)
app.conf.update(
    task_default_queue="cw1-ingestion",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    task_soft_time_limit=240,
    task_time_limit=270,
    broker_transport_options={"visibility_timeout": 300, "socket_timeout": 3, "socket_connect_timeout": 3},
    broker_connection_timeout=3,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    task_publish_retry=False,
)


@app.task(name="citeweave.ingest")
def ingest(job_id):
    from citeweave.ingestion import run_ingestion

    run_ingestion(job_id)


@app.task(name="citeweave.evaluate_case")
def evaluate_case(eval_id, case_id):
    from citeweave.evaluation.service import run_case

    run_case(eval_id, case_id)
