"""Record a project-only cold restart or allowlisted runtime/cost observations."""

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone

import httpx
import psutil
from sqlalchemy import select

from citeweave.db import engine, transaction
from citeweave.domain import QueryRunRow, VersionRow
from citeweave.settings import ROOT


def ready_versions():
    with transaction() as db:
        return sorted(str(v) for v in db.scalars(select(VersionRow.id).where(VersionRow.status == "READY")))


def docker_rows(*args):
    result = subprocess.run(
        ["docker", *args, "--format", "{{json .}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=20,
    )
    return [json.loads(line) for line in result.stdout.splitlines() if line]


def restart():
    shell = shutil.which("pwsh")
    if not shell:
        raise RuntimeError("PowerShell_7_required")
    before = ready_versions()
    engine().dispose()
    steps = []
    for action in ("Stop", "Up"):
        started = time.monotonic()
        # A detached Windows gateway can inherit pipe handles after pwsh exits.
        # Real log files let us wait for the launcher exit without waiting for pipe EOF.
        with (ROOT / f".runtime/logs/restart-{action}.log").open("wb") as log:
            result = subprocess.run(
                [shell, "-NoProfile", "-File", "scripts/m1.ps1", "-Action", action],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                timeout=300,
            )
        if result.returncode:
            raise RuntimeError("restart_step_failed_" + action)
        step = {"action": action, "seconds": round(time.monotonic() - started, 2), "exit_code": 0}
        if action == "Stop":
            step["project_running_containers"] = [
                row["Names"] for row in docker_rows("ps") if row["Names"].startswith("citeweave-m0-")
            ]
            assert not step["project_running_containers"]
            # Windows may time out, rather than reject a connection, after a listener exits.
            # Inspect actual listeners instead of treating a network timeout as proof of exit.
            step["gateway_offline"] = not any(
                c.status == psutil.CONN_LISTEN and c.laddr.port == 18081
                for c in psutil.net_connections(kind="tcp")
            )
            assert step["gateway_offline"], "gateway_still_listening_after_stop"
        steps.append(step)
    health = httpx.get("http://127.0.0.1:18080/health/ready", timeout=5, trust_env=False)
    health.raise_for_status()
    after = ready_versions()
    assert before == after
    return {"steps": steps, "ready_before": before, "ready_after": after, "api_health": health.json()}


def snapshot():
    containers = [
        {k: v for k, v in r.items() if k in ("Names", "State", "Status", "Ports")}
        for r in docker_rows("ps", "-a")
        if r["Names"].startswith(("citeweave-", "docker-"))
    ]
    memory = [
        {k: v for k, v in r.items() if k in ("Name", "MemUsage", "MemPerc", "CPUPerc", "PIDs")}
        for r in docker_rows("stats", "--no-stream")
        if r["Name"].startswith("citeweave-")
    ]
    models = []
    for process in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
        info = process.info
        if (info["name"] or "").lower() != "python.exe":
            continue
        if any(arg.replace("\\", "/").endswith("scripts/model_gateway.py") for arg in info["cmdline"] or []):
            models.append({"pid": info["pid"], "rss_mib": round(info["memory_info"].rss / 2**20, 2)})
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=10,
    ).stdout.strip()
    with transaction() as db:
        runs = [
            {
                "id": str(r.id),
                "status": r.status,
                "created_at": r.created_at.isoformat(),
                "usage": r.usage,
                "estimated_yuan": float(r.estimated_yuan) if r.estimated_yuan is not None else None,
                "reserved_yuan": float(r.reserved_yuan),
                "actual_account_debit": "unavailable",
            }
            for r in db.scalars(select(QueryRunRow).order_by(QueryRunRow.created_at))
        ]
    return {
        "containers": containers,
        "container_memory": memory,
        "gateway_processes": models,
        "host_available_mib": round(psutil.virtual_memory().available / 2**20, 2),
        "gpu_device_total_observation": gpu,
        "query_runs": runs,
        "estimated_yuan_sum_known": sum(r["estimated_yuan"] or 0 for r in runs),
        "actual_account_debit": "unavailable",
        "measurement_scope": "instantaneous; Docker VM overhead excluded; GPU includes other apps",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    report = {"at": datetime.now(timezone.utc).isoformat(), **(restart() if args.restart else snapshot())}
    target = ROOT / ("docs/reports/m1-restart.json" if args.restart else "docs/reports/m1-runtime.json")
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target.name + " saved")
