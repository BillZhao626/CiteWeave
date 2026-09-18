"""Secret-free source/environment contract. Dirty diagnostics are not release evidence."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime, timezone

from citeweave.settings import ROOT

ENVIRONMENT_KEYS = {
    "services",
    "image_digests",
    "hardware",
    "topology",
    "models",
    "dataset",
    "corpus",
    "artifacts",
    "profile",
    "prompt",
    "limits",
    "cost_visibility",
}


def source_identity(root=ROOT):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()

    paths = git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    allowed = ("src/", "scripts/", "migrations/", "prompts/", "evals/", "benchmarks/", "tests/", "corpus/")
    hashes = {
        p: hashlib.sha256((root / p).read_bytes()).hexdigest()
        for p in sorted(set(paths))
        if p.startswith(allowed) and (root / p).is_file()
    }
    return dict(
        commit=git("rev-parse", "HEAD"),
        tree=git("rev-parse", "HEAD^{tree}"),
        dirty=bool(git("status", "--porcelain")),
        source_hashes=hashes,
        allowlist_sha256=hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
    )


def create(environment, concurrency=1, requests=2, warmup=0, provider="mock", budget_yuan=0):
    if provider not in {"mock", "real"} or provider == "real" and budget_yuan <= 0:
        raise ValueError("real_provider_requires_explicit_budget")
    if set(environment) != ENVIRONMENT_KEYS:
        raise ValueError("benchmark_environment_incomplete")
    result = dict(
        schema_revision="benchmark-manifest-v1",
        timestamp=datetime.now(timezone.utc).isoformat(),
        timezone="UTC",
        source=source_identity(),
        lockfiles={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                *ROOT.glob("*.lock"),
                *ROOT.glob("*lock*.yaml"),
                *ROOT.joinpath("apps/web").glob("*lock*.yaml"),
                *ROOT.joinpath("benchmarks").glob("*lock*.yaml"),
            ]
        },
        runtime=dict(
            os=platform.platform(),
            python=platform.python_version(),
            celery=importlib.metadata.version("celery"),
            node=subprocess.check_output(["node", "--version"], text=True).strip(),
        ),
        environment=environment,
        concurrency=concurrency,
        request_count=requests,
        warmup=warmup,
        seed=0,
        order="fixed_input_closed_loop",
        provider=provider,
        budget_yuan=budget_yuan,
        cache_policy="no_retrieval_cache",
    )
    validate(result)
    return result


def validate(value, final=False):
    required = {
        "schema_revision",
        "timestamp",
        "timezone",
        "source",
        "lockfiles",
        "runtime",
        "environment",
        "concurrency",
        "request_count",
        "warmup",
        "seed",
        "order",
        "provider",
        "budget_yuan",
        "cache_policy",
    }
    if set(value) != required or set(value["environment"]) != ENVIRONMENT_KEYS:
        raise ValueError("benchmark_manifest_incomplete")
    if (
        not 1 <= value["concurrency"] <= 16
        or not 1 <= value["request_count"] <= 10000
        or not 0 <= value["warmup"] <= 100
    ):
        raise ValueError("benchmark_workload_limit")
    if final and (value["source"]["dirty"] or not all(value["environment"].values())):
        raise ValueError("benchmark_release_identity_incomplete")
    if final:
        contracts = {
            "services": {"postgresql", "redis", "qdrant"},
            "hardware": {"cpu", "gpu", "memory_bytes"},
            "topology": {"api", "worker", "gateway"},
            "models": {"embedding", "reranker"},
            "dataset": {"id", "split", "sha256"},
            "corpus": {"manifest_sha256", "source_hashes"},
            "prompt": {"revision", "sha256"},
            "limits": {"request_deadline_seconds", "max_active_queries", "model_queue_limit"},
            "cost_visibility": {"provider", "actual_charge", "usage"},
        }
        for key, fields in contracts.items():
            if not fields <= value["environment"][key].keys():
                raise ValueError("benchmark_release_environment_incomplete:" + key)
        for model in value["environment"]["models"].values():
            if not {"model", "revision", "device", "precision", "tokenizer"} <= model.keys():
                raise ValueError("benchmark_model_identity_incomplete")
        if not value["lockfiles"] or not value["source"]["source_hashes"]:
            raise ValueError("benchmark_source_freeze_incomplete")
    if value["provider"] not in {"mock", "real"}:
        raise ValueError("benchmark_provider_mode")
    if value["provider"] == "real" and value["budget_yuan"] <= 0:
        raise ValueError("real_provider_requires_explicit_budget")
    return value
