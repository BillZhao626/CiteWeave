"""Evaluation must preserve each product profile's input contract before I/O."""

import asyncio
import hashlib
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from citeweave.evaluation import execution
from citeweave.settings import ROOT
from citeweave.trace import runtime_config


@pytest.mark.parametrize(
    ("profile", "kind", "length", "expected"),
    [
        ("m3-context", "single_fact", 49, "auto"),
        ("m3-context", "comparison", 160, "auto"),
        ("m3-context", "comparison", 161, None),
        ("telecom-structural-v1", "comparison", 161, "compare"),
        ("telecom-structural-v1", "single_fact", 49, "single"),
    ],
)
def test_evaluator_uses_profile_contract(monkeypatch, profile, kind, length, expected):
    config = dict(
        runtime_config(profile),
        index_bindings={},
        judge_profile="judge-v4",
        judge_prompt_sha256=hashlib.sha256((ROOT / "prompts/judge-v4.txt").read_bytes()).hexdigest(),
    )
    evaluation = SimpleNamespace(
        dataset_id="fixture",
        dataset_hash="fixture",
        runtime_config=config,
        workspace_id=uuid4(),
        kb_id=uuid4(),
    )
    saved = SimpleNamespace(result={}, query_run_id=None, execution_attempt=1)

    @contextmanager
    def transaction():
        yield None

    monkeypatch.setattr(execution, "transaction", transaction)
    monkeypatch.setattr(execution.lifecycle, "owned", lambda *args: (saved, evaluation, None))
    monkeypatch.setattr(
        execution,
        "load_dataset",
        lambda _: (
            {"cases": [{"case_id": "case", "question": "x" * length, "question_type": kind}]},
            "fixture",
        ),
    )
    captured = []

    class ReachedQuery(Exception):
        pass

    def begin(workspace, body, *args, **kwargs):
        captured.append(body)
        raise ReachedQuery

    monkeypatch.setattr(execution.answering, "begin_query", begin)
    with pytest.raises(ReachedQuery if expected else ValidationError):
        asyncio.run(execution.execute_case(uuid4(), "case", uuid4()))
    assert [b.evidence_mode for b in captured] == ([expected] if expected else [])
