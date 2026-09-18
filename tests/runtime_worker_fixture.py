"""Explicit test-only Celery entry point: real ingestion/retrieval/PG, mock paid providers.

Never loaded by the application worker. The harness supplies an original fixture manifest.
"""

import hashlib
import json
import os
from pathlib import Path

from citeweave import answering
from citeweave.celery_app import app
from citeweave.evaluation import service

fixture = Path(os.environ["CW_RUNTIME_FIXTURE"])


def record(kind):
    with fixture.with_suffix(".calls").open("a", encoding="utf-8") as out:
        out.write(kind + "\n")


class MockProvider:
    async def stream(self, messages):
        record("answer")
        evidence = json.loads(messages[-1]["content"])["evidence"]
        chosen = next(e for e in evidence if "30 秒" in e["text"])
        yield {"text": "湖畔站每 30 秒采样 [" + chosen["label"] + "]。"}
        yield {"usage": {"prompt_tokens": 10, "completion_tokens": 10}, "model": "mock-runtime"}


async def mock_judge(*args):
    record("judge")
    return dict(status="COMPLETED", estimated_yuan=0, method="mock_runtime_only", scores=None)


def load_fixture(dataset_id):
    assert dataset_id == "original-runtime-fixture"
    raw = fixture.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


answering.DeepSeekProvider = MockProvider
service.assess_answer = mock_judge
service.load_dataset = load_fixture

__all__ = ["app"]
