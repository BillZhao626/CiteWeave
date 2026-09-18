"""Destructive only to citeweave-m0 worker/broker processes; all volumes retained."""

import subprocess
import time
from uuid import uuid4

from common import ROOT, configure, report

configure()
from citeweave import jobs
from citeweave.tasks import app


def compose(*args):
    result = subprocess.run(
        ["docker", "compose", "--env-file", ".env", "-f", "deploy/compose.m0.yml", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode:
        raise RuntimeError(f"compose {args}: {result.stderr[-1500:]}")


def until(predicate, seconds=45):
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        if predicate():
            return round(time.monotonic() - start, 3)
        time.sleep(0.5)
    raise AssertionError("recovery_deadline_exceeded")


def main():
    jobs.initialize()
    checks = {}
    scope = str(uuid4())
    try:
        compose("stop", "broker")
        identity, _ = jobs.submit(scope, "broker-outage", {"value": "survived"})
        start = time.monotonic()
        delivery = jobs.dispatch(app)
        assert delivery["error_type"] is not None
        assert jobs.get_job(identity)["status"] == "queued"
        checks["broker_outage"] = {
            "durable_queued": True,
            "failure_seconds": time.monotonic() - start,
            "publisher_error": delivery["error_type"],
        }
    finally:
        compose("start", "broker")
    jobs.dispatch(app)
    until(lambda: jobs.get_job(identity)["status"] == "completed")
    checks["broker_outage"]["recovered"] = True
    print("P03 broker outage recovered", flush=True)

    for key, payload, trigger in [
        ("kill_running", {"pause_before": 60}, "running"),
        ("kill_after_commit_before_ack", {"pause_after": 60}, "completed"),
    ]:
        identity, _ = jobs.submit(scope, key, payload)
        jobs.dispatch(app)
        until(lambda: jobs.get_job(identity)["status"] == trigger)
        old = jobs.get_job(identity)
        compose("kill", "-s", "SIGKILL", "worker")
        compose("up", "-d", "--force-recreate", "worker")
        if trigger == "running":
            time.sleep(9)
            jobs.reconcile()
            jobs.dispatch(app)
        else:
            # Deliberate at-least-once redelivery as well as the broker's unacked redelivery.
            app.send_task("citeweave.execute", args=[identity], retry=False)

        def converged():
            with jobs.connect() as db:
                owners = db.execute(
                    "SELECT count(DISTINCT owner) AS n FROM cw_job_events WHERE job_id=%s", (identity,)
                ).fetchone()["n"]
            return jobs.get_job(identity)["status"] == "completed" and owners >= 2

        elapsed = until(converged)
        new = jobs.get_job(identity)
        with jobs.connect() as db:
            effects = db.execute(
                "SELECT count(*) AS n FROM cw_effects WHERE job_id=%s", (identity,)
            ).fetchone()["n"]
        assert effects == 1
        checks[key] = {
            "new_worker_delivery": True,
            "effective_results": effects,
            "attempts_before": old["attempts"],
            "attempts_after": new["attempts"],
            "convergence_poll_seconds": elapsed,
            "job_id": identity,
        }
        print(f"P03 {key} recovered", flush=True)
    import pytest

    result = pytest.main(["tests/test_jobs.py", "-q"])
    assert result == 0
    checks["database_invariants"] = (
        "concurrency16 + conflict + expired lease + stale fence + duplicate commit"
    )
    report(
        "p03-recovery",
        {
            "status": "passed",
            "checks": checks,
            "limitation": "M0 deterministic effect only; no cancellation/external side-effect certification",
        },
    )


if __name__ == "__main__":
    main()
