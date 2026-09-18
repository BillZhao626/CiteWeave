# Product benchmark harness

Stage C runs small engineering smoke workloads. Formal quality comparisons,
the 96-case evaluation, paid-provider concurrency and capacity-8 acceptance
belong to Stage D. No measured speedup or quality improvement is implied.

Use an isolated migrated database with the accepted source blobs, published
Qdrant bindings and resident pinned E5/BGE gateway. The Python modules import
the actual product retriever/answering code. Keep configuration in environment
variables; never pass credentials in CLI arguments or commit runtime output.

Create a manifest with `benchmarks.manifest.create(environment, ...)`. Its
environment contract requires services, image digests, hardware, process
topology, model/revision/device/precision/tokenizer identity, corpus and dataset
hashes, captured artifact/index identities, profile, prompt, limits and cost
visibility. `limits.request_deadline_seconds` bounds each driver operation.
Unknown values must be explicit in diagnostics; a dirty source is ineligible
for a final release report. Freeze the manifest immediately before execution.

```powershell
python -m benchmarks.end_to_end --manifest private-manifest.json --questions independent-perf-pool.json --kb <uuid> --workspace <uuid> --output new-private-run
python -m benchmarks.retrieval --manifest private-manifest.json --questions independent-perf-pool.json --kb <uuid> --workspace <uuid> --output new-private-retrieval-run
python -m benchmarks.report new-private-run
python -m benchmarks.initialization --python <model-python> --model-path <pinned-snapshot> --device cuda --count 3
pnpm --dir benchmarks install --frozen-lockfile
pnpm --dir benchmarks exec playwright test ui_e2e.spec.ts --list
```

The default answer provider is deterministic mock generation over real retrieved
evidence. Paid requests require both `--provider real` and `--budget-yuan`, with
matching frozen manifest values; the product's monthly reservation cap still
applies. No Holdout pool is allowed. Retrieval-only diagnostic QueryRuns have
`benchmark_retrieval_only` as their terminal reason and do not pretend to be
completed answers. Fresh-process initialization needs the same pinned model,
device, precision, input and batch as the resident gateway; OS disk-cache state
is uncontrolled and reported. Do not infer a resident comparison unless those
identities match. The full prescribed initialization matrix remains Stage D.

UI driver: set `CW_BENCH_UI_URL`, `CW_BENCH_KB`, `CW_BENCH_TOKEN`,
`CW_BENCH_PROVIDER=mock`, and a new `CW_BENCH_OUTPUT` directory. The server must
be an isolated product API configured with mock generation. The default is eight
independent browser contexts and five operations each; override
`CW_BENCH_CONTEXTS`/`CW_BENCH_ROUNDS` for a small smoke. These are browser
sessions, not people. The driver exercises existing UI, SSE, citation/PDF and
trace routes, and changes only the request's selectable retrieval profile.
The full 40-operation workload is not a Gate-C4 requirement.

Each new run preserves manifest, every raw request, stages, deterministic
summary, report and artifact hashes. Arrival includes admission waits; success
latency and all-request termination latency are separate. Throughput divides
successful completions by first-arrival to last-finish wall time. Warmup rows
remain in raw data and are excluded from measured summaries. Percentiles use
nearest-rank; P99 is omitted below 1,000 measured samples. Forty UI operations
can show exploratory P95/max, never production P99 or an SLA. The closed-loop
driver can exhibit coordinated omission. Failures, cancellation, timeout and
429 rows must remain in the report.
