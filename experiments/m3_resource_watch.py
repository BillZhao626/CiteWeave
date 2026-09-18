"""Sample local resources around a named experiment; never record process command lines."""

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.label.replace("-", "").isalnum() or not args.command:
        raise ValueError("invalid_experiment_command")
    destination = ROOT / "docs/reports/m3-revisit" / (args.label + "-resources.json")
    if destination.exists():
        raise ValueError("resource_report_exists")
    samples, errors = [], []
    start = time.perf_counter()
    child = subprocess.Popen(args.command, cwd=ROOT)
    while True:
        memory = psutil.virtual_memory()
        sample = dict(
            elapsed_seconds=round(time.perf_counter() - start, 3), available_ram_mib=memory.available / 2**20
        )
        rss, private = [], []
        for proc in psutil.process_iter(["name", "cmdline", "memory_info"]):
            try:
                args_ = proc.info.get("cmdline") or []
                if any("scripts/model_gateway.py" in s.replace("\\", "/") for s in args_):
                    rss.append(proc.info["memory_info"].rss / 2**20)
                    private.append(getattr(proc.info["memory_info"], "private", 0) / 2**20)
            except (psutil.Error, TypeError):
                continue
        sample["gateway_family_rss_mib"] = sum(rss) if rss else None
        sample["gateway_private_commit_mib"] = sum(private) if private else None
        try:
            raw = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                text=True,
                timeout=5,
            )
            used, utilization = map(float, raw.strip().splitlines()[0].split(","))
            sample.update(device_vram_used_mib=used, device_utilization=utilization)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            errors.append(type(exc).__name__)
        samples.append(sample)
        if child.poll() is not None:
            break
        time.sleep(1)
    result = dict(
        at=datetime.now(timezone.utc).isoformat(),
        label=args.label,
        exit_code=child.returncode,
        wall_seconds=round(time.perf_counter() - start, 3),
        samples=samples,
        sampling_errors=errors,
        scope="Approximate 1-second samples of whole NVIDIA device and Windows model gateway process family RSS; RSS is not committed memory. Docker processes not included in gateway RSS; minima/peaks can miss transients.",
    )
    try:
        with urllib.request.urlopen("http://127.0.0.1:18081/health", timeout=3) as response:
            result["gateway_at_end"] = json.load(response)
    except (OSError, ValueError):
        result["gateway_at_end"] = None
    for key in ("device_vram_used_mib", "gateway_family_rss_mib", "gateway_private_commit_mib"):
        values = [s[key] for s in samples if s.get(key) is not None]
        result["peak_" + key] = max(values) if values else None
    result["minimum_available_ram_mib"] = min(s["available_ram_mib"] for s in samples)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "samples"}), flush=True)
    raise SystemExit(child.returncode)


if __name__ == "__main__":
    main()
