# ADR 0001: isolate attempt indices and keep M1 infrastructure bounded

Original: immutable snapshots + outbox/fencing; local blob adapter; replaceable models. M0 has no integrated version pipeline.

Problem: DB fencing alone cannot stop a late worker from overwriting Qdrant points. Shared sparse vocabulary/IDF also cannot be mixed between independently built snapshots. Windows GPU inference should not be loaded separately into every worker/API process on a 16 GB laptop.

Alternatives: shared collection with mutable active flags; whole-KB rebuild on every upload; one physical collection per attempt. Choose per-attempt collections with deterministic chunk IDs and a PostgreSQL-published active version/collection pointer. Queries only resolve committed pointers. Costs: extra abandoned collections and small-document rank bias; cap 10 active document snapshots in M1 and leave storage reclamation/KB-wide snapshot compaction to later work. All abandoned collections are ineffective even if a stale process writes again.

Qdrant supports Query API sparse/hybrid and built-in RRF. Keep M0 app fusion because its one-based k=60 convention and trace are already tested and differ from server defaults. SDK calls remain in an adapter. Source: https://qdrant.tech/documentation/search/hybrid-queries/ (checked 2026-09-13).

Choose one authenticated local GPU model gateway, concurrency 1, shared by API/worker. Keep one PostgreSQL, Valkey and Qdrant; no MinIO/Temporal. Serve compiled React static assets alongside API for the single-machine launcher; React remains an independent build and consumes HTTP only. GPU runtime can later move to a separate container/host without changing domain interfaces. Development deployment and actual RAM will be tested, not assumed.
