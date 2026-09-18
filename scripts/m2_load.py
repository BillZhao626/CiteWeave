"""Controlled gateway concurrency, resource sampling and embedding-cache upper-bound measurement."""

import json
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import psutil

from citeweave.evaluation.dataset import load_dataset
from citeweave.settings import ROOT, settings


def resources():
    models = []
    for process in psutil.process_iter(["name", "cmdline", "memory_info"]):
        try:
            args = " ".join(process.info["cmdline"] or []).replace("\\", "/")
            if "scripts/model_gateway.py" in args and ROOT.as_posix().lower() in args.lower():
                models.append(process.info["memory_info"].rss / 2**20)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    values = [float(v.strip()) for v in gpu.stdout.strip().split(",")] if gpu.returncode == 0 else []
    return dict(
        host_available_mib=psutil.virtual_memory().available / 2**20,
        gateway_rss_mib=sum(models),
        gpu_device_used_mib=values[0] if values else None,
        gpu_device_total_mib=values[1] if values else None,
    )


def main():
    dataset, _ = load_dataset()
    texts = list(dict.fromkeys(g["quote"][:160] for c in dataset["cases"] for g in c["gold"]))[:20]
    headers = {"Authorization": "Bearer " + settings().gateway_token()}
    url = settings().model_url
    samples, stop = [], threading.Event()

    def sample():
        while not stop.is_set():
            samples.append(resources())
            stop.wait(0.5)

    def call(number):
        start = time.perf_counter()
        route = "/embed" if number % 2 == 0 else "/rerank"
        payload = (
            {"texts": texts[:16]}
            if route == "/embed"
            else {"question": "这些标准如何定义互操作要求与时间格式？", "texts": texts}
        )
        try:
            response = httpx.post(url + route, json=payload, headers=headers, timeout=20, trust_env=False)
            status, code = (
                response.status_code,
                response.json().get("error") if response.content and response.status_code != 200 else None,
            )
        except httpx.HTTPError as exc:
            status, code = 0, type(exc).__name__
        return dict(
            route=route, latency_ms=(time.perf_counter() - start) * 1000, http_status=status, error_code=code
        )

    warm = [call(0), call(1)]
    assert all(c["http_status"] == 200 for c in warm), "gateway_warmup_failed"
    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    scenarios = []
    try:
        for concurrency, count in [(1, 8), (2, 12), (4, 16), (8, 24)]:
            start = time.perf_counter()
            with ThreadPoolExecutor(concurrency) as pool:
                results = list(pool.map(call, range(count)))
            latencies = sorted(r["latency_ms"] for r in results)
            scenario = dict(
                concurrency=concurrency,
                requests=count,
                seconds=time.perf_counter() - start,
                succeeded=sum(r["http_status"] == 200 for r in results),
                failed=sum(r["http_status"] != 200 for r in results),
                p50_ms=statistics.median(latencies),
                p95_ms=latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))],
                requests_detail=results,
            )
            scenarios.append(scenario)
            print(json.dumps({k: v for k, v in scenario.items() if k != "requests_detail"}), flush=True)
        repeated = []
        for _ in range(12):
            start = time.perf_counter()
            response = httpx.post(
                url + "/embed",
                json={"texts": ["RFC 3339 的小时范围是什么？"], "query": True},
                headers=headers,
                timeout=15,
                trust_env=False,
            )
            response.raise_for_status()
            repeated.append((time.perf_counter() - start) * 1000)
    finally:
        stop.set()
        thread.join(timeout=10)
    report = dict(
        at=datetime.now(timezone.utc).isoformat(),
        profile="one GPU inference; FIFO max four waiters; eight handler threads; request read deadline 5s; queue deadline 8s",
        warmup=warm,
        scenarios=scenarios,
        resource_samples=samples,
        resources=dict(
            min_host_available_mib=min(s["host_available_mib"] for s in samples),
            max_gateway_rss_mib=max(s["gateway_rss_mib"] for s in samples),
            max_gpu_device_used_mib=max(s["gpu_device_used_mib"] or 0 for s in samples),
        ),
        repeated_query_embedding_ms=repeated,
        repeated_query_embedding_p50_ms=statistics.median(repeated),
        cache_measurement="Maximum possible saved embedding latency only; compare with actual M2 query traces before cache decision.",
        scope="Local controlled workload, not QPS promise; device GPU includes display/other apps; peak sampling 0.5s plus command overhead.",
        gateway_after=httpx.get(url + "/health", timeout=3, trust_env=False).json(),
        provider_calls=0,
    )
    (ROOT / "docs/reports/m2-load.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("LOAD REPORT SAVED", flush=True)


if __name__ == "__main__":
    main()
