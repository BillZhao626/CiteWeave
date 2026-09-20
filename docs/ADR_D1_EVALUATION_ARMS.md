# Frozen D1 experiment arms

This prerequisite exposes the Stage-B comparison in evaluation infrastructure,
without new public query profiles or a Development quality revision. No quality
case was executed before the prerequisite readiness checks and local commit.

B0/B1 share one call to the product HybridRetriever. Its captured pre-packaging
trace and six legacy seeds feed the unchanged m3-context policy for B0 and the
same geometric neighbor traversal for B1. B1 accepts only complete spans when
the actual legacy user-message JSON (including labels and question) fits 6,400
characters, 96 spans and 2,048 pinned BGE proxy tokens. It is not a simple change
to the old text-character limit. Each pack records its policy revision.

The legacy experiment uses frozen source/canonical bytes with the original
glyph160 function; only its explicit document count ceiling is raised to
100,000. The normal default remains 1,000. The canonical parser is not rerun.
An isolated database retains the original source/version/scope IDs; private
Qdrant collections use `cw_d1_glyph_` names. E5, BM25, RRF and BGE behavior are
unchanged. The baseline is called `legacy-glyph-large-v1`, not a byte-identical
historical release. Index write transport aggregates ten unchanged 20-text
embedding batches; this changes neither vectors nor retrieval configuration.

T1/T2 share one product StructuralRetriever draw with real BGE. The evaluation
captures validated pre-selection inputs and executes seed selection with
Parent disabled for T1, then executes the original complete selection with
Parent enabled for T2. It asserts identical branches, pool, scores, ranking,
snapshot and seeds. Normal callers retain `parent_expansion=True` and do not
capture replay inputs. T1 is not a fault injection or post-filtered T2 pack.
The Development RRF attribution reorders only the same BGE-input pool and
executes seed selection separately; it is not a product profile.

Only immutable corpus tables are copied to an isolated structural evaluation
database. Their indexes remain the accepted, read-only structural collections.
Artifacts are copied as draft and published after their members are copied in
one transaction, respecting immutable publication triggers. Accepted product
connections are not interrupted. No shared schema changes are required.

Each arm has a PostgreSQL QueryRun with case, batch, policy, code identity and
shared-retrieval lineage. Retrieval-only terminal rows use the existing FAILED
state with `evaluation_retrieval_only`, as the benchmark does, and a separate
runtime-config retrieval outcome. They do not fabricate completed answers.
Actual model calls belong to the shared draw's trace, rather than being billed
twice to each packaging arm. Source-support assessment calls the existing
Assessor/support functions. Physical span probes use product citation_for;
final answer Citation validity is N/A until answer generation occurs.

Commands (with src, repository and scripts on PYTHONPATH):

1. Set `CW_D1_OUTPUT` to the private evidence directory and run
   `python scripts/prepare_d1_legacy.py`.
2. Run `python scripts/d1_phase1.py readiness --output <private-readiness-dir>`.
   These two non-dataset queries prove pairing and real model availability.
3. After focused tests and readiness pass, commit the prerequisite once.
4. Run `python scripts/d1_phase1.py evaluate --output <private-matrix-dir>`.
   Dirty source is rejected; only the explicitly named 72-case visible dataset
   is loaded. Then `python scripts/report_d1_phase1.py <private-matrix-dir>`.

The scripts clear the answer key and have no answer/judge execution path.
Existing BLOCKED artifacts are retained outside new output subdirectories.
This change does not authorize Holdout, performance benchmarks, answer quality
or final candidate promotion. Source-support metric definitions are unchanged.
