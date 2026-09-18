"""Isolated local source-install rehearsal; preserves the main stack and its data."""

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from citeweave.settings import ROOT

STATE = ROOT / ".runtime/m3-clean-state.json"


def run(command, cwd, log, steps, label, timeout=1800):
    started = time.monotonic()
    with log.open("wb") as output:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=output,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
    steps.append(
        dict(step=label, seconds=round(time.monotonic() - started, 2), exit_code=completed.returncode)
    )
    print(label + (" PASS" if completed.returncode == 0 else " FAILED (local log)"), flush=True)
    if completed.returncode:
        raise RuntimeError("clean_step_failed: " + label)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    shell = shutil.which("pwsh")
    assert shell, "PowerShell_7_required"
    if args.prepare:
        assert not STATE.exists(), "clean_rehearsal_already_prepared"
        subprocess.run([sys.executable, "scripts/public_candidate.py", "--stage-only"], cwd=ROOT, check=True)
        staged = json.loads((ROOT / ".runtime/releases/latest.json").read_text(encoding="utf-8"))
        source = Path(staged["source"]).resolve()
        assert source.is_relative_to((ROOT / ".runtime/releases").resolve())
        identity = uuid4().hex[:12]
        folder = ROOT / ".runtime" / ("clean-m3-" + identity)
        shutil.copytree(source, folder)
        assert not any((folder / p).exists() for p in (".env", ".venv", ".runtime", "apps/web/node_modules"))
        model_root = folder / ".cache/huggingface/hub"
        for name in ("models--intfloat--multilingual-e5-small", "models--BAAI--bge-reranker-v2-m3"):
            shutil.copytree(ROOT / ".cache/huggingface/hub" / name, model_root / name)
        state = dict(
            folder=str(folder),
            project="cw3-clean-" + identity,
            source_manifest=staged["directory"] + "/manifest.json",
            steps=[],
            boundary="Fresh source/venvs/node_modules/credentials/database/volumes; only public model download cache and package/image caches reused; same physical Windows machine.",
        )
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        try:
            run(
                [shell, "-NoProfile", "-File", "scripts/m1.ps1", "-Setup", "-InstallOnly"],
                folder,
                folder / "install.log",
                state["steps"],
                "fresh_locked_install",
            )
        finally:
            STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return
    state = json.loads(STATE.read_text(encoding="utf-8"))
    folder = Path(state["folder"]).resolve()
    assert folder.is_relative_to((ROOT / ".runtime").resolve()) and folder.name.startswith("clean-m3-")
    assert state["steps"] and state["steps"][-1]["exit_code"] == 0, "install_not_complete"
    from sqlalchemy import select

    from citeweave.db import engine, transaction
    from citeweave.domain import EvalRunRow, IngestionJobRow, QueryRunRow

    with transaction() as db:
        for model, statuses in (
            (EvalRunRow, ["PENDING", "RUNNING"]),
            (QueryRunRow, ["RUNNING"]),
            (IngestionJobRow, ["QUEUED", "PARSING", "EMBEDDING", "INDEXING"]),
        ):
            assert db.scalar(select(model.id).where(model.status.in_(statuses)).limit(1)) is None, (
                "main_work_in_progress"
            )
    engine().dispose()
    clean_py = str(folder / ".venv/Scripts/python.exe")
    project = state["project"]
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "--env-file",
        ".env",
        "-f",
        "deploy/compose.m0.yml",
        "-f",
        "deploy/compose.m1.yml",
    ]
    state.update(at=datetime.now(timezone.utc).isoformat(), status="FAIL")
    try:
        run(
            [shell, "-NoProfile", "-File", "scripts/m1.ps1", "-Action", "Stop"],
            ROOT,
            folder / "main-stop.log",
            state["steps"],
            "main_stop",
        )
        run(
            [clean_py, "experiments/bootstrap.py"],
            folder,
            folder / "bootstrap.log",
            state["steps"],
            "new_credentials",
        )
        run(
            compose + ["up", "-d", "--wait", "postgres", "broker", "qdrant"],
            folder,
            folder / "empty-services.log",
            state["steps"],
            "new_volumes",
        )
        run(
            [clean_py, "scripts/clean_probe.py", "--before-migration"],
            folder,
            folder / "empty-schema.log",
            state["steps"],
            "empty_schema",
        )
        run(
            [shell, "-NoProfile", "-File", "scripts/m1.ps1", "-ProjectName", project],
            folder,
            folder / "clean-up.log",
            state["steps"],
            "clean_startup",
        )
        run(
            [clean_py, "scripts/verify.py", "--milestone", "m3"],
            folder,
            folder / "verify.log",
            state["steps"],
            "clean_all_gates",
        )
        run(
            [clean_py, "scripts/clean_probe.py"],
            folder,
            folder / "smoke.log",
            state["steps"],
            "clean_original_smoke",
        )
        state["probe"] = json.loads((folder / ".runtime/clean-probe.json").read_text(encoding="utf-8"))
        state["gates"] = json.loads((folder / "docs/reports/m3-gates.json").read_text(encoding="utf-8"))
        state["status"] = "PASS"
    finally:
        try:
            run(
                [shell, "-NoProfile", "-File", "scripts/m1.ps1", "-ProjectName", project, "-Action", "Stop"],
                folder,
                folder / "clean-stop.log",
                state["steps"],
                "clean_stop",
            )
        finally:
            run(
                [shell, "-NoProfile", "-File", "scripts/m1.ps1", "-Action", "Up"],
                ROOT,
                folder / "main-restore.log",
                state["steps"],
                "main_restored",
            )
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            (ROOT / "docs/reports/m3-clean-install.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    print("Clean installation rehearsal " + state["status"], flush=True)


if __name__ == "__main__":
    main()
