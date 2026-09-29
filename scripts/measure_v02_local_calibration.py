"""One-shot, local-only annotation counting; no product or provider imports.

The caller must enforce wall time and RSS externally. Windows Job limits enforce
CPU and committed memory before any manifest is read. --self-test uses only tiny
Unicode/format values, never the fixed manifest. Failed validation consumes the
single attempt. Human semantic review is never inferred from these checks.
"""

import argparse
import ctypes
import hashlib
import json
import os
import statistics
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

LIMIT = 512 * 1024 * 1024
JOB_HANDLE = None


def now():
    return datetime.now().astimezone().isoformat()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def size(text):
    data = text.encode("utf-8")
    return {"utf8_bytes": len(data), "codepoints": len(text), "sha256": digest(data)}


def write(path, value):
    # An enrichment write must never truncate the already durable core receipt.
    staging = path.with_suffix(path.suffix + ".tmp")
    try:
        with staging.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, path)
    finally:
        if staging.exists():
            staging.unlink()


def auxiliary_metadata():
    """Explicit local allowlist; failures are isolated per optional field."""
    result = {"environment": {}, "auxiliary_failures": []}
    fields = {
        "python": lambda: sys.version,
        "os": lambda: str(sys.getwindowsversion()) if os.name == "nt" else "UNAVAILABLE",
        "cpu": lambda: os.environ.get("PROCESSOR_IDENTIFIER", "UNAVAILABLE"),
        "logical_cpu_count": os.cpu_count,
    }
    for name, collect in fields.items():
        try:
            value = collect()
            result["environment"][name] = value if value is not None else "UNAVAILABLE"
        except Exception as exc:
            result["environment"][name] = "UNAVAILABLE"
            result["auxiliary_failures"].append({"field": name, "type": type(exc).__name__})
    try:
        result["peak_rss_bytes"] = peak_rss()
    except Exception as exc:
        result["peak_rss_bytes"] = "UNAVAILABLE"
        result["auxiliary_failures"].append({"field": "peak_rss_bytes", "type": type(exc).__name__})
    return result


def finalize(path, receipt, collect=auxiliary_metadata, persist=write):
    receipt["core_persisted_at"] = now()
    persist(path, receipt)  # fsync + replace completes before any optional collector
    try:
        auxiliary = collect()
    except Exception as exc:
        auxiliary = {
            "environment": "UNAVAILABLE",
            "peak_rss_bytes": "UNAVAILABLE",
            "auxiliary_failures": [{"field": "collector", "type": type(exc).__name__}],
        }
    receipt["auxiliary"] = auxiliary
    receipt["sealed_at"] = now()
    persist(path, receipt)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def guard():
    """Fail closed unless Windows CPU/memory limits can be installed."""
    global JOB_HANDLE
    require(os.name == "nt", "Windows external resource supervisor required")

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong),
            ("job_time", ctypes.c_longlong),
            ("flags", wintypes.DWORD),
            ("min_ws", ctypes.c_size_t),
            ("max_ws", ctypes.c_size_t),
            ("active", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ("ro", "wo", "oo", "rb", "wb", "ob")]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io", IO),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t),
            ("peak_job", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    JOB_HANDLE = kernel.CreateJobObjectW(None, None)
    require(bool(JOB_HANDLE), "job creation failed")
    limits = Extended()
    # 890 seconds leaves headroom within the aggregate 900 CPU-second ceiling.
    limits.basic.process_time = 890 * 10_000_000
    limits.basic.flags = 0x2 | 0x8 | 0x100  # process time, active processes, process memory
    limits.basic.active = 1
    limits.process_memory = LIMIT
    require(
        kernel.SetInformationJobObject(JOB_HANDLE, 9, ctypes.byref(limits), ctypes.sizeof(limits)),
        "job limits unavailable",
    )
    require(kernel.AssignProcessToJobObject(JOB_HANDLE, kernel.GetCurrentProcess()), "job assignment failed")

    def deny_network(event, args):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
            raise RuntimeError("local-only measurement forbids network and subprocesses")

    sys.addaudithook(deny_network)


def peak_rss():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in ("peak_ws", "ws", "peak_pool", "pool", "peak_nonpool", "nonpool", "page", "peak_page")
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    require(
        psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb),
        "RSS accounting unavailable",
    )
    return counters.peak_ws


def strings(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings(item, path + "/" + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from strings(item, path + "/" + str(index))


def envelope(value):
    whole = size(encoded(value))
    components = {key: size(encoded(item)) for key, item in value.items()}
    raw = {path: size(text) for path, text in strings(value)}
    for unit in ("utf8_bytes", "codepoints"):
        whole["outer_labels_and_separators_" + unit] = whole[unit] - sum(c[unit] for c in components.values())
        whole["serialization_and_nonstring_metadata_" + unit] = whole[unit] - sum(
            s[unit] for s in raw.values()
        )
    whole["string_escape_increment_bytes"] = sum(
        len(encoded(text).encode()) - len(text.encode()) - 2 for _, text in strings(value)
    )
    whole["components"] = components
    whole["raw_strings"] = raw
    whole["within_local_workload_ceiling"] = whole["utf8_bytes"] <= 65536
    return whole


def measure(manifest, receipt, root):
    require(manifest["batch"] == "local-first-01", "wrong batch")
    families = manifest["families"]
    require([f["id"] for f in families] == [f"F{i}" for i in range(1, 7)], "six prescribed families required")
    require([len(f["targets"]) for f in families] == [1, 2, 2, 2, 1, 2], "wrong target allocation")
    require(len(manifest["coverage_18"]) == 18, "coverage mapping incomplete")
    for path, expected in manifest["public_inputs"].items():
        require(digest((root / path).read_bytes()) == expected, "public input hash mismatch: " + path)
    require(
        manifest["public_inputs"]["docs/V02_LOCAL_CALIBRATION_EXECUTION_PLAN.md"]
        == receipt["authorization"]["plan_sha256"],
        "accepted plan hash mismatch",
    )
    results = {}
    distributions = {}
    for family in families:
        require(len(family["history"]) <= 16, "scope limitation: history workload ceiling")
        sources = {s["id"]: s for s in family["history"]}
        require(len(sources) == len(family["history"]), "duplicate source identity")
        require(
            [s["turn"] for s in family["history"]] == list(range(1, len(sources) + 1)), "accepted sequence"
        )
        for source in sources.values():
            require(source["conversation"] == family["id"], "cross-conversation source")
            require(source["span"] == [0, len(source["text"])], "source span mismatch")
            require(source["sha256"] == digest(source["text"].encode()), "source hash mismatch")
            require(
                source["accepted_reference"] and not source["runtime_accepted"], "reference status mismatch"
            )
        distances = []
        for target in family["targets"]:
            tid = target["id"]
            require(tid not in results, "duplicate target")
            head = target["head"]
            require(0 <= head <= len(sources), "head range")
            require(target["target_sequence"] == head + 1, "target sequence mismatch")
            require(
                target["head_turn"] == (f"{family['id']}.T{head}" if head else None), "head identity mismatch"
            )
            groups = []
            required = set()
            for group in target["required_groups"]:
                alternatives = []
                for alternative in group["alternatives"]:
                    require(bool(alternative), "empty source alternative")
                    values = []
                    for sid in alternative:
                        require(
                            sid in sources and sources[sid]["turn"] <= head, "source missing or after head"
                        )
                        distance = head + 1 - sources[sid]["turn"]
                        values.append({"source": sid, "accepted_turn_distance": distance})
                        required.add(sid)
                        distances.append(distance)
                    alternatives.append(
                        {
                            "sources": values,
                            "complete_alternative_distance": max(v["accepted_turn_distance"] for v in values),
                        }
                    )
                groups.append(
                    {
                        "group": group["id"],
                        "alternatives": alternatives,
                        "indivisible": group["indivisible"],
                        "supersession_edges": group["supersession_edges"],
                    }
                )
            require(required == set(target["mandatory_original_sources"]), "mandatory original mismatch")
            require(not required.intersection(target["forbidden_sources"]), "mandatory/forbidden conflict")
            for sid in target["forbidden_sources"] + target["optional_sources"]:
                require(
                    sid in sources and sources[sid]["turn"] <= head, "optional/forbidden reference missing"
                )
            for edge in target["supersession_edges"]:
                require(edge["from"] in required and edge["to"] in required, "incomplete correction edge")
                require(sources[edge["from"]]["turn"] < sources[edge["to"]]["turn"], "cyclic correction edge")
            for projection in target["state_projection"]:
                require(set(projection["source_refs"]) <= required, "state provenance mismatch")
            pack = target["reference_pack"]
            for doc in pack["span_ledger"]:
                require(doc["document_id"] in target["scope"], "reference evidence outside scope")
                require(digest(doc["canonical_text"].encode()) == doc["canonical_sha256"], "canonical hash")
                a, b = doc["span"]
                require(doc["canonical_text"][a:b] == doc["quote"], "evidence quote span")
            require(
                all(
                    s["version"] in {d["version_id"] for d in pack["span_ledger"]}
                    for s in pack["payload"]["sources"]
                ),
                "pack source identity",
            )
            for evidence in pack["payload"]["evidence"]:
                require(evidence["text"] in {d["quote"] for d in pack["span_ledger"]}, "pack text mismatch")
            for env in target["envelopes"].values():
                require(env["original_query"] == target["query"], "query changed in envelope")
                require(env["constraints"]["scope"] == target["scope"], "envelope scope mismatch")
                require(env["state_projection"] == target["state_projection"], "state envelope mismatch")
                require(
                    [g["group_id"] for g in env["history_groups"]]
                    == [g["id"] for g in target["required_groups"]],
                    "group envelope mismatch",
                )
                for group in env["history_groups"]:
                    for s in group["sources"]:
                        require(
                            s == dict(sources[s["id"]], head_ref=target["head_turn"]),
                            "source envelope mismatch",
                        )
            require(target["envelopes"]["generation"]["reference_evidence_pack"] == pack, "pack truncated")
            require(
                bool(target["assertions"]) and bool(target["forbidden_assumptions"]), "missing assertions"
            )
            require(
                target["ambiguity"] == (target["expected_outcome"] == "clarification"), "ambiguity contract"
            )
            require(target["self_contained"] == (len(groups) == 0), "self-contained annotation mismatch")
            sizes = {name: envelope(value) for name, value in target["envelopes"].items()}
            boundary = {}
            if family["id"] == "F6":
                for name, metrics in sizes.items():
                    length = metrics["utf8_bytes"]
                    boundary[name] = {
                        "L": length,
                        "hypothetical_byte_cap_checks": [
                            {"cap": cap, "complete_payload_fits": length <= cap}
                            for cap in (length - 1, length, length + 1)
                        ],
                        "runtime_verified": False,
                    }
            identities = [dict(sources[s], head_ref=target["head_turn"]) for s in sorted(required)]
            results[tid] = {
                "manifest_ref": f"families/{family['id']}/targets/{tid}",
                "M01": {"rule": "R01", "groups": groups},
                "M03": {
                    "rule": "R03",
                    "required_groups": len(groups),
                    "optional_groups": len(target["optional_sources"]),
                    "forbidden_sources": target["forbidden_sources"],
                    "source_identities": identities,
                    "indivisible_groups": [g["group"] for g in groups if g["indivisible"]],
                    "dedup_relationships": target["dedup_relationships"],
                    "state_projection": target["state_projection"],
                },
                "M04": {"rule": "R04", "envelopes": sizes, "static_boundaries": boundary},
                "M07_pre": {
                    "rule": "R07",
                    "record_consistency": "PASS",
                    "checks": [
                        "provenance",
                        "scope",
                        "head",
                        "correction_graph",
                        "mandatory",
                        "state_sources",
                        "self_contained",
                        "ambiguity",
                        "forbidden_assumptions",
                    ],
                    "expected_outcome_annotation": target["expected_outcome"],
                    "semantic_review": "PROVISIONAL",
                    "runtime_verified": False,
                },
            }
        distributions[family["id"]] = {
            "raw_distances": distances,
            "denominator": "required source occurrence per target/alternative; paired views",
            "min": min(distances) if distances else None,
            "median": statistics.median(distances) if distances else None,
            "max": max(distances) if distances else None,
            "ecdf": [
                {"distance": d, "count_le": sum(v <= d for v in distances), "denominator": len(distances)}
                for d in sorted(set(distances))
            ],
        }
    receipt["rules"] = {
        "R01": "target=head+1; distance=target-source accepted-reference ordinal; retain every chain member and alternative",
        "R03": "all required groups needed; alternative is complete source set; exact identity includes head/scope/version/span/hash; projection does not replace originals",
        "R04": "UTF-8 LF JSON ensure_ascii=False sort_keys=True separators=(',',':'); bytes/codepoints/SHA256 only; string values exclude object keys; overhead includes keys/syntax/nonstring metadata; no token inference",
        "R07": "reference/hash/graph consistency only; annotation meaning requires Product Owner; no runtime proof",
    }
    receipt["targets"] = results
    receipt["M01_family_distributions"] = distributions
    receipt["M02"] = manifest["M02"]
    receipt["deferred"] = {
        "M05": "UNAVAILABLE_NONBLOCKING locally; real output usage/reserve requires real slice and provider Gate",
        "M06": "DEFER_TO_POST_VERTICAL_SLICE; actual Conversation PG queries and I/O needed",
        "M07_runtime": "DEFER_TO_POST_VERTICAL_SLICE; real transaction/recovery/fencing tests needed",
        "generation_tokens": "UNAVAILABLE; verified tokenizer/full messages/capacity/reserve remain gated",
        "baseline_pilot": "NOT AUTHORIZED; not executed",
    }
    receipt["candidate_ranges"] = {
        "status": "UNFROZEN",
        "values": [],
        "reason": "constructed annotation breakpoints only; no reviewed quality or real cost axis",
    }
    receipt["measurement_status"] = (
        "DONE"
        if all(
            env["within_local_workload_ceiling"]
            for t in results.values()
            for env in t["M04"]["envelopes"].values()
        )
        else "PARTIAL: measurement limited/incomplete; no truncation or product overflow inference"
    )


def main():
    start = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--external-supervisor", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    audited_events = []
    if args.self_test:

        def observe(event, values):
            if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
                audited_events.append(event)

        sys.addaudithook(observe)
    guard()
    if args.self_test:
        require(size("中😀\n")["utf8_bytes"] == 8 and size("中😀\n")["codepoints"] == 3, "Unicode check")
        require(encoded({"b": "\n", "a": "中"}) == '{"a":"中","b":"\\n"}', "serialization check")
        auxiliary = auxiliary_metadata()
        require(not auxiliary["auxiliary_failures"], "safe allowlist/RSS microcheck failed")
        writes = []

        def save_micro(path, value):
            writes.append(json.loads(encoded(value)))

        def fail_optional():
            require(
                len(writes) == 1 and writes[0]["measurement_status"] == "DONE", "core must precede metadata"
            )
            raise RuntimeError("injected optional metadata failure")

        finalize(None, {"measurement_status": "DONE", "tiny": "中😀"}, fail_optional, save_micro)
        require(
            len(writes) == 2 and writes[1]["measurement_status"] == "DONE", "core survives optional failure"
        )
        require(writes[1]["auxiliary"]["environment"] == "UNAVAILABLE", "optional failure must be explicit")
        require(not audited_events, "socket/subprocess event during self-test")
        print(
            encoded(
                {
                    "self_test": "PASS",
                    "safe_environment": auxiliary["environment"],
                    "socket_subprocess_events": audited_events,
                    "optional_failure_ordering": "PASS: tiny in-memory persistence-order check; no manifest read",
                    "wall_seconds": time.perf_counter() - start,
                    "cpu_seconds": time.process_time(),
                    "peak_rss_bytes": peak_rss(),
                }
            )
        )
        return
    require(args.external_supervisor, "external wall/RSS supervisor required")
    require(args.manifest is not None and args.receipt is not None, "explicit manifest and receipt required")
    receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
    require(receipt["measurement_attempts"] == 0, "attempt already consumed; no rerun authorized")
    receipt["measurement_attempts"] = 1
    receipt["measurement_started_at"] = now()
    receipt["status"] = "MEASUREMENT_STARTED"
    write(args.receipt, receipt)  # durable attempt record before reading/validating the fixed manifest
    try:
        raw = args.manifest.read_bytes()
        receipt["manifest_sha256"] = digest(raw)
        require(len(raw) <= 1024 * 1024, "manifest workload ceiling")
        manifest = json.loads(raw)
        repo = Path(__file__).resolve().parents[1]
        input_bytes = len(raw) + sum((repo / p).stat().st_size for p in manifest["public_inputs"])
        require(input_bytes <= 2 * 1024 * 1024, "input workload ceiling")
        receipt["input_bytes"] = input_bytes
        measure(manifest, receipt, repo)
        receipt["status"] = "MEASURED; local exit and separate Human Review amendment to be evaluated"
    except Exception as exc:
        receipt["status"] = "CAL PARTIAL / INCONCLUSIVE"
        receipt["measurement_status"] = "FAILED; no automatic rerun"
        receipt["failure"] = {"type": type(exc).__name__, "reason": str(exc)}
    receipt["measurement_finished_at"] = now()
    receipt["compute"] = {
        "wall_seconds_adapter": time.perf_counter() - start,
        "cpu_seconds_adapter": time.process_time(),
        "limits": "external wall/RSS; Windows Job 890 CPU seconds/512 MiB commit/1 process",
    }
    finalize(args.receipt, receipt)

    print(encoded({"status": receipt["status"], "measurement_status": receipt["measurement_status"]}))
    return 1 if "failure" in receipt else 0


if __name__ == "__main__":
    sys.exit(main())
