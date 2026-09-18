"""Run explicitly against the dedicated Compose DB: pytest tests/test_jobs.py --run integration is unnecessary.

These tests are skipped unless CW_DATABASE_URL is set by the experiment runner.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from citeweave import jobs

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_DATABASE_URL"), reason="needs M0 DB"),
]


def test_concurrent_idempotency_and_conflict():
    jobs.initialize()
    scope = str(uuid4())
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: jobs.submit(scope, "same", {"x": 1}), range(16)))
    assert len({r[0] for r in results}) == 1
    assert sum(r[1] for r in results) == 1
    with pytest.raises(ValueError, match="idempotency_conflict"):
        jobs.submit(scope, "same", {"x": 2})


def test_stale_fence_and_expired_lease_cannot_commit():
    jobs.initialize()
    identity, _ = jobs.submit(str(uuid4()), "fence", {})
    a = jobs.claim(identity, "old")
    assert jobs.claim(identity, "duplicate") is None
    with jobs.connect() as db:
        db.execute("UPDATE cw_jobs SET lease_until=now()-interval '1 second' WHERE id=%s", (identity,))
    assert not jobs.complete(identity, a["fence"], {"stale": True})
    b = jobs.claim(identity, "new")
    assert b["fence"] > a["fence"]
    assert not jobs.complete(identity, a["fence"], {"stale": True})
    assert jobs.complete(identity, b["fence"], {"ok": True})
    assert not jobs.complete(identity, b["fence"], {"duplicate": True})
    with jobs.connect() as db:
        assert (
            db.execute("SELECT count(*) AS n FROM cw_effects WHERE job_id=%s", (identity,)).fetchone()["n"]
            == 1
        )
