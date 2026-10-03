"""Complete unsigned owner review surface; no rubric scores are AI approvals."""

from citeweave.evaluation.dev_arms import ARM_IDS, arm
from citeweave.evaluation.dev_dataset import DATASET_HASH


def review_plan(data, *, approval=None):
    if approval is not None and (
        approval.get("decision") != "APPROVE"
        or approval.get("dataset_sha256") != DATASET_HASH
        or approval.get("approved_views") != {v.id: v.sha256 for v in data.views}
    ):
        raise ValueError("review_approval_binding_mismatch")
    units = [dict(id=f"LABEL:{v.id}", kind="label", view=v.id, mandatory=True) for v in data.views]
    units.extend(
        dict(id=f"OUTPUT:{v.id}:{a}", kind="output", view=v.id, arm=a, mandatory=True)
        for v in data.views
        for a in ARM_IDS[2:]
    )
    units.extend(
        dict(id=f"DISPUTE:{v.id}", kind="adjudication", view=v.id, mandatory=False) for v in data.views
    )
    for unit in units:
        unit.update(owner_decision=None, actual_minutes=None, owner_identity=None, reviewed_hash=None)
        if approval is not None and unit["kind"] == "label":
            unit.update(
                owner_decision="APPROVE",
                owner_identity=approval["reviewer_role"],
                reviewed_hash=approval["approved_views"][unit["view"]],
                review_date=approval["review_date"],
                duration_status="NOT_MEASURED",
            )
    return dict(
        units=units,
        maximum_units=48,
        maximum_minutes=384,
        data_review_status="APPROVED_FROZEN" if approval else "PENDING",
        label_units_completed=12 if approval else 0,
        actual_label_review_minutes=None,
        workload_reconciliation="PENDING_CUMULATIVE_PRIOR_REVIEWS_AND_UNMEASURED_DURATION",
        predecessor_review=dict(
            decision=data.predecessor["owner_decision"],
            manifest=data.predecessor,
            actual_units=None,
            actual_minutes=None,
            accounting="OWNER_ACTUAL_WORKLOAD_REQUIRED_NO_POOL_RESET",
        ),
        output_review_status="NOT_RUN",
        rule="All critical/hard/failure/guard/disputed decision outputs mandatory; stop before pool exhaustion. No extra units or automatic rereview.",
    )


def review_surface(data, *, approval=None):
    review_plan(data, approval=approval)  # Reject a mismatched supplied record.
    out = [
        "# v0.2a DEV — Product Owner data review",
        "",
        "Status: **PENDING — AI-authored proposals, not approved Human Gold**. DEV/HARD/REG NOT_RUN; provider/model/Judge calls 0.",
        f"Manifest: `{data.dataset_id}` / SHA256 `{DATASET_HASH}`.",
        f"Version {data.version}. Predecessor: `{data.predecessor}`. Human first review: **REVISE**, preserved in V02_DEV_DATA_REVIEW_V1.md and V02_DEV_READINESS_V1.md. Current revision remains unsigned.",
        "V2 and its Test-first audit remain historical: V02_DEV_DATA_REVIEW_V2.md / V02_DEV_READINESS_V2.md / V02_DEV_TEST_FIRST_AUDIT.md. Owner resolves only D1.V2 topic_relation=return: T3 shifts current focus to tray-display; target returns to D1-task. Pending/active semantic State availability is independent of conversational topic movement. This is not full-dataset Human Gold approval.",
        "Owner revision 2026-10-01: recent-2 covers ALL raw members in R/A. D1.V2/D3.V1 A may use accepted active bounded State for intent/rewrite without old raw recovery, B credit or Evidence authority. D3.V2 R/A still fail incomplete atomic correction groups. AB0 old/group recovery is B. D4.V2 has no required raw-history denominator.",
        "State-only A outputs are evaluation artifacts, NOT product acceptances. The unchanged production interpreter/commit requires raw intent provenance; no acceptance is fabricated or published. All diagnostic answers still use validated current EvidencePack. Live State-only acceptance integration remains a separate execution gate.",
        "Original fictional engineering examples, AI-assisted, MIT. No legacy/CAL/REG/Holdout content used. The owner must validate family connectivity, differences and all reference labels; physical quote validity does not prove semantic support.",
        "Review all 12 label units below before freezing accepted labels. For each: APPROVE / REVISE / REJECT, reviewer, date, exact manifest/view hash, actual minutes, changes/reason. Fields remain blank until owner action. Changed labels require a new byte/hash revision; no accepted protocol rewrite.",
        "Shared review pool ceiling remains 48 units / 384 minutes. The prior REVISE review actual units/minutes are not supplied; Owner must reconcile cumulative consumption before further review/execution. This revision does not reset the pool or invent consumed units. Outputs NOT_RUN; stop before cumulative pool exhaustion.",
        "D6 token L−1/L/L+1 fixtures test capacity separately; they are not additional paid views or semantic quality results.",
        f"Prewritten D4 clarification branch: {data.closed_loop_branch}. Fixed-prefix and closed-loop are separate reports; a branch not taken leaves D4.V2 planned/NOT_RUN. Owner review covers this branch in D4 label units.",
        "",
        "## Arm identities",
        "",
    ]
    for a in ARM_IDS:
        config = arm(a)
        out.append(
            f"- `{a}`: N={config.n}, state={config.state}, B={config.b}, C={config.c}, K={config.k}; config SHA `{config.config_hash}`."
        )
    for view in data.views:
        out.extend(
            [
                "",
                f"## {view.id} — {view.primary_category}",
                "",
                f"Family {view.family}; HARD={view.hard}; categories: {', '.join(view.categories)}.",
                f"View SHA256 `{view.sha256}`.",
                "Fixed prefix controls are manually accepted intent/clarification seeds, with no model calls or technical-answer evidence. Each arm rebuilds its own Conversation and accepts every prefix using PostgreSQL; state enabled only A/AB0.",
                "",
            ]
        )
        for p in view.prefix:
            out.append(
                f"- {p.id}: {p.question} Scope: {', '.join(p.scope)}. Control: {p.control}. Signals: {p.signals.model_dump_json()}. State: {[(s.kind, s.key, s.value, s.replaces) for s in p.state]}. Correction of: {p.correction or 'none'}."
            )
        if not view.prefix:
            out.append("- Empty prefix (single-turn control).")
        out.extend(
            [
                f"- Target: **{view.question}**",
                "",
                f"Target scope: {', '.join(view.scope)} (immutable version IDs below).",
                f"Dependency: `{view.dependency}`; topic: `{view.topic_relation}`; outcome: `{view.outcome}`.",
                f"Required source groups: {[(g.id, g.alternatives, g.old) for g in view.required_history] or 'none; N/A coverage denominator'}. Irrelevant: {list(view.irrelevant_history)}.",
                f"Intended facts (source prefix/CURRENT): {list(view.facts)}. Protected terms: {list(view.protected)}.",
                f"Expected behavior: {view.reference}",
                f"Reference answer draft (citation labels resolve against current pack): {view.reference_answer}",
                f"Required aspects: {list(view.required_aspects)}. Allowed equivalence: {' '.join(view.allowed_equivalence)}.",
                f"R/A limitations: {view.diagnostic_limits or 'recent-2 all-member rule applies; no old raw closure'}.",
            ]
        )
        for sid, start, end in view.evidence_support:
            source = next(s for s in data.sources if s.id == sid)
            out.append(
                f"Support `{sid}` [{start}, {end}): `{source.text[start:end]}`. Quote is exact; owner reviews semantic support separately."
            )
        for a in view.assertions:
            out.append(f"- {a.id} [{a.severity}/{a.dimension}]: {a.statement}")
        out.extend(
            [
                "",
                "Owner decision: ______; reviewer/date: ______; reviewed hash: ______; actual minutes: ______; reason/changes: ______.",
            ]
        )
    out.extend(["", "## Original immutable sources", ""])
    for source in data.sources:
        out.extend(
            [
                f"### {source.id}",
                "",
                f"Document `{source.document_id}`; DocumentVersion `{source.version_id}`.",
                f"PDF SHA `{source.pdf_sha256}`; canonical SHA `{source.canonical_sha256}`; normalized PDF box `{source.pdf_box}`.",
                f"Local reproducible PDF: `.runtime/evaluation/v02-dev-sources/{source.id}.pdf` (ignored; regenerate only from `scripts/author_v02_dev.py`).",
                "",
                "```text",
                source.text,
                "```",
                "",
            ]
        )
    out.extend(
        [
            "## Coverage and owner checks",
            "",
            "18 category rows are listed below. Empty categories are gaps, not implicitly covered. Boundary/adversarial coverage comes from separate deterministic L1 tests; long context uses controlled complete-message boundaries, not a population-long-conversation claim.",
        ]
    )
    for category, views in data.category_coverage.items():
        out.append(f"- {category}: {', '.join(views) or 'no paid view; L1 supplement only'}")
    out.extend(
        [
            "",
            "Owner family/connectivity and independent-provenance review: ______.",
            "Owner full-dataset APPROVE / REVISE / REJECT: ______; reviewer/date: ______; reviewed manifest SHA: ______; total label-review minutes: ______.",
            "Approval of this dataset is not permission to run DEV or call a provider. Output reserves, verified accounting/identity/rates, finite authorization and operational runtime gates remain separate.",
            "",
        ]
    )
    surface = "\n".join(out)
    if approval:
        from citeweave.evaluation.dev_approval import APPROVAL_ID, APPROVAL_SHA256

        header = (
            "# v0.2a DEV v3 — Human Gold APPROVED / FROZEN\n\n"
            f"Human Product Owner APPROVE, 2026-10-01; 12 LABEL units. Approval `{APPROVAL_ID}` "
            f"/ SHA256 `{APPROVAL_SHA256}`. Actual minutes **NOT_MEASURED**; personal name not supplied.\n\n"
            f"Exact dataset `{data.dataset_id}` / version {data.version} / SHA256 `{DATASET_HASH}`. "
            "Original manifest PENDING fields remain historical bytes; separate pinned attestation is authoritative. "
            "DEV/HARD/REG NOT_RUN; no provider/model/Judge outcomes used to tune this version; paid execution NOT authorized. "
            "Future defects require preserved v3/results and a new version/hash plus new Human review.\n\n"
            "The full reviewed surface is preserved below as the pre-approval proposal. Blank proposal fields are historical; "
            "the external attestation records APPROVE for each exact view hash. Human semantic data approval does not "
            "make fake outputs real provider results or independently blinded data. All four caveats are retained in the approval.\n\n"
            "## Approved label units\n\n| View | Reviewed SHA256 | Decision | Reviewer/date | Minutes |\n"
            "| --- | --- | --- | --- | --- |\n"
        )
        for v in data.views:
            header += (
                f"| {v.id} | `{v.sha256}` | APPROVE | Human Product Owner / 2026-10-01 | NOT_MEASURED |\n"
            )
        surface = header + "\n## Historical proposal surface (superseded status)\n\n" + surface
    return surface
