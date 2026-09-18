"""One container supervises Celery plus a DB-driven recovery/dispatch loop."""

import logging
import signal
import subprocess
import sys
import threading

from citeweave.celery_app import evaluate_case, ingest
from citeweave.evaluation.service import reconcile as reconcile_evaluations
from citeweave.ingestion_state import reconcile


def main():
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "citeweave.celery_app:app",
            "worker",
            "--loglevel=WARNING",
            "--concurrency=1",
            "--queues=cw-ingestion,cw-evaluation",
            "--hostname=cw1-%h",
        ]
    )
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    try:
        while not stop.is_set():
            if child.poll() is not None:
                raise RuntimeError("celery_process_exited")
            try:
                reconcile(lambda job: ingest.apply_async(args=[job], retry=False))
                reconcile_evaluations(
                    lambda eval_id, case: evaluate_case.apply_async(args=[eval_id, case], retry=False)
                )
            except Exception as exc:
                logging.error(
                    "recovery_loop_failed class=%s; next periodic check will retry", type(exc).__name__
                )
            stop.wait(2)  # Normal bounded polling cadence; recovery uses DB lease deadlines, not this delay.
    finally:
        child.terminate()
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


if __name__ == "__main__":
    main()
