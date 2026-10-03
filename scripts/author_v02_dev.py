"""Reproduce original review proposals and PDFs; never run a candidate/provider.

PDFs are ignored local fixture assets, reproducible with locked reportlab. Existing
fixture authoring conventions (invariant PDF, normalized bbox, exact text) apply.
No sealed/legacy/CAL dataset is opened. Run this BEFORE code/dataset review only.
"""

import hashlib
import io
import re
import textwrap
from pathlib import Path

import pdfplumber
from reportlab.pdfgen import canvas

from citeweave.evaluation.dev_dataset import DATASET_ID, HARD, canonical, digest, identity

ROOT = Path(__file__).resolve().parents[1]
TEXT = {
    "D1.manual": "Ferrule-Q requires a nine-minute cooldown before optical inspection. Thermal Tray-R uses a separate four-minute standby cycle.",
    "D2.manual": "Grove-Panel records an alarm by illuminating its amber indicator. Orchard-Clock calibration uses a violet status marker and does not govern Grove-Panel alarms.",
    "D3.manual": "Cobalt-Latch release amber uses a three-notch alignment. Cobalt-Latch release violet uses a five-notch alignment. Display framing does not change latch alignment.",
    "D4.manual": "Beacon-North displays a blue indicator after a valve test. Beacon-South displays a green indicator after a valve test. Neither unit is a default selection.",
    "D5.manual": "Quill m4 must not relay before 24 hours have elapsed after initialization. At or after 24 hours, Quill m4 may relay if its isolation check passes.",
    "D6.ledger": "Sable-Pump maintenance ledgers record scheduled service dates and cycle counts. This ledger defines no brownout contingency.",
    "D6.contingency": "During a brownout, Sable-Pump must switch to the gravity bypass. Scheduled service records do not define or replace this contingency.",
}
CATEGORIES = (
    "simple follow-up",
    "pronoun/coreference",
    "omitted entity",
    "old-but-relevant",
    "new-but-irrelevant noise",
    "topic shift",
    "topic return",
    "user correction",
    "constraint supersession",
    "ambiguous reference",
    "no-rewrite-needed",
    "rewrite-required",
    "rewrite-danger / negation",
    "document-scope change",
    "evidence-insufficient",
    "long conversation / context pressure",
    "single-turn regression",
    "boundary/adversarial supplement",
)
REFERENCE_ANSWERS = {
    "D1.V1": "Ferrule-Q requires a nine-minute cooldown before optical inspection. [E1]",
    "D1.V2": "Ferrule-Q requires a nine-minute cooldown before optical inspection. [E1]",
    "D2.V1": "Grove-Panel records an alarm by illuminating its amber indicator. [E1]",
    "D2.V2": "Grove-Panel records an alarm by illuminating its amber indicator. [E1]",
    "D3.V1": "Cobalt-Latch release amber uses a three-notch alignment. [E1]",
    "D3.V2": "Cobalt-Latch release violet uses a five-notch alignment. [E1]",
    "D4.V1": "Which unit do you mean: Beacon-North or Beacon-South?",
    "D4.V2": "Beacon-South displays a green indicator after a valve test. [E1]",
    "D5.V1": "No. Quill m4 must not relay before 24 hours have elapsed after initialization. [E1]",
    "D5.V2": "Yes: it must NOT relay before 24 hours have elapsed after initialization. [E1]",
    "D6.V1": "During a brownout, Sable-Pump must switch to the gravity bypass. [CURRENT_SOURCE_LABEL]",
    "D6.V2": "证据不足，无法回答。",
}


def pdf_source(sid, text):
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(612, 792), invariant=1, pageCompression=0)
    pdf.setTitle(sid)
    pdf.setAuthor("CiteWeave original AI-assisted fixture; MIT")
    pdf.setFont("Helvetica", 11)
    lines = textwrap.wrap(text, 80)
    for i, line in enumerate(lines):
        pdf.drawString(48, 720 - i * 18, line)
    pdf.showPage()
    pdf.save()
    raw = output.getvalue()
    with pdfplumber.open(io.BytesIO(raw)) as parsed:
        canonical_text = parsed.pages[0].extract_text()
    assert canonical_text == "\n".join(lines)
    local = ROOT / ".runtime/evaluation/v02-dev-sources"
    local.mkdir(parents=True, exist_ok=True)
    (local / (sid + ".pdf")).write_bytes(raw)
    return dict(
        id=sid,
        family=sid[:2],
        document_id=str(identity(sid + ":document")),
        version_id=str(identity(sid + ":version:1")),
        text=canonical_text,
        canonical_sha256=hashlib.sha256(canonical_text.encode()).hexdigest(),
        pdf_sha256=hashlib.sha256(raw).hexdigest(),
        pdf_box=[48 / 612, (792 - 732) / 792, 568 / 612, (792 - (720 - (len(lines) - 1) * 18) + 4) / 792],
        provenance="original_AI_assisted_MIT_review_pending",
    )


def prefix(pid, question, task=None, entities=(), state=(), correction=None, scope=(), control="intent_seed"):
    return dict(
        id=pid,
        question=question,
        signals=dict(topic=task, task=task, entities=list(entities), constraints=[]),
        state=list(state),
        correction=correction,
        scope=list(scope),
        control=control,
    )


def value(key, text, kind="entity", replaces=None):
    return dict(key=key, kind=kind, value=text, replaces=replaces)


def main():
    sources = [pdf_source(sid, text) for sid, text in TEXT.items()]
    lookup = {s["id"]: s for s in sources}
    views = []

    def add(
        family,
        variant,
        question,
        history,
        *,
        categories,
        dependency="required",
        facts=(),
        groups=(),
        irrelevant=(),
        relation="continue",
        scope=None,
        outcome="documentary_answer",
        reference,
        aspects=(),
        support=None,
        protected=(),
        limits=None,
    ):
        sid = family + ".manual" if family != "D6" else "D6.ledger"
        view_id = family + ".V" + str(variant)
        if view_id == "D1.V2":
            relation = "return"
            reference += (
                " Topic relation is return from tray-display to D1-task; pending/active "
                "Working State availability is independent of conversational focus."
            )
        scope = scope or [sid]
        evidence = []
        if support:
            source_id, proposition = support
            # Exact canonical source offsets, including preserved PDF line breaks.
            match = re.search(
                r"\s+".join(re.escape(word) for word in proposition.split()), lookup[source_id]["text"]
            )
            if match is None:
                raise ValueError("original_source_proposition_missing")
            evidence = [[source_id, match.start(), match.end()]]
        assertions = [
            dict(
                id=view_id + ":intent",
                dimension="interpretation",
                statement="Bind only the intended current entity/constraint; preserve scope and explicit terms.",
                severity="critical",
            ),
            dict(
                id=view_id + ":memory",
                dimension="Memory/Evidence",
                statement="History/state is non-Evidence; use only current authorized immutable source support.",
                severity="critical",
            ),
            dict(id=view_id + ":behavior", dimension="outcome", statement=reference, severity="critical"),
        ]
        v = dict(
            id=view_id,
            family=family,
            primary_category=categories[0],
            categories=list(categories),
            hard=view_id in HARD,
            prefix=history,
            question=question,
            scope=scope,
            query_signals=dict(topic=family + "-task", task=family + "-task", entities=[], constraints=[]),
            required_history=[
                dict(id=view_id + ":G" + str(i + 1), alternatives=[list(members)], old=old)
                for i, (members, old) in enumerate(groups)
            ],
            irrelevant_history=list(irrelevant),
            facts=[list(f) for f in facts],
            protected=[list(p) for p in protected],
            dependency=dependency,
            topic_relation=relation,
            outcome=outcome,
            reference=reference,
            reference_answer=REFERENCE_ANSWERS[view_id],
            required_aspects=list(aspects),
            evidence_support=evidence,
            assertions=assertions,
            allowed_equivalence=[
                "Equivalent wording preserving every critical/material assertion; alternate documentary support requires blinded owner adjudication."
            ],
            diagnostic_limits=limits or {},
            state_only_intent=view_id in {"D1.V2", "D3.V1"},
        )
        v["sha256"] = digest(v)
        views.append(v)

    p1 = prefix(
        "T1",
        "For D1-task inspection, use Ferrule-Q.",
        "D1-task",
        ("Ferrule-Q",),
        (value("unit", "Ferrule-Q"),),
        scope=("D1.manual",),
    )
    neutral = prefix("T2", "Keep the D1-task inspection request pending.", scope=("D1.manual",))
    noise = prefix(
        "T3",
        "Now check Thermal Tray-R's standby display.",
        "tray-display",
        ("Thermal Tray-R",),
        scope=("D1.manual",),
    )
    for n, history in ((1, [p1, neutral]), (2, [p1, neutral, noise])):
        add(
            "D1",
            n,
            "For the D1-task inspection, how long must it cool?",
            history,
            categories=("pronoun/coreference", "simple follow-up", "omitted entity")
            if n == 1
            else ("old-but-relevant", "new-but-irrelevant noise", "pronoun/coreference"),
            facts=(("entity", "Ferrule-Q", "T1"),),
            groups=((("T1",), n == 2),),
            irrelevant=("T2",) if n == 1 else ("T2", "T3"),
            reference="Resolve it to Ferrule-Q; answer nine-minute cooldown; do not inherit Tray-R's four-minute standby.",
            aspects=("Ferrule-Q", "nine-minute cooldown before optical inspection"),
            support=("D1.manual", "Ferrule-Q requires a nine-minute cooldown before optical inspection."),
            limits={}
            if n == 1
            else {
                "cp-r-v1": "source unavailable; no guessed binding",
                "cp-a-v1": "Resolve Ferrule-Q from active bounded State only; no T1 raw text, raw coverage or B credit; current Evidence only",
            },
        )

    old = prefix(
        "T1",
        "Discuss Orchard-Clock calibration first.",
        "orchard-calibration",
        ("Orchard-Clock",),
        scope=("D2.manual",),
    )
    for n, h in ((1, []), (2, [old])):
        add(
            "D2",
            n,
            "How does Grove-Panel record an alarm?",
            h,
            categories=("no-rewrite-needed", "single-turn regression")
            if n == 1
            else ("topic shift", "no-rewrite-needed"),
            dependency="none",
            relation="continue" if n == 1 else "shift",
            irrelevant=() if n == 1 else ("T1",),
            reference="Use original self-contained query, skip interpretation dispatch, answer amber indicator, exclude Orchard calibration.",
            aspects=("Grove-Panel", "amber indicator"),
            support=("D2.manual", "Grove-Panel records an alarm by illuminating its amber indicator."),
        )

    old = prefix(
        "T1",
        "For D3-task latch testing, use Cobalt-Latch release amber.",
        "D3-task",
        ("Cobalt-Latch release amber",),
        (value("release", "Cobalt-Latch release amber"),),
        scope=("D3.manual",),
    )
    noise1 = prefix("T2", "Discuss unrelated display framing.", "display-framing", scope=("D3.manual",))
    noise2 = prefix("T3", "Continue the display discussion.", "display-framing", scope=("D3.manual",))
    correction = prefix(
        "T4",
        "Correction for D3-task: use Cobalt-Latch release violet, replacing amber.",
        "D3-task",
        ("Cobalt-Latch release violet",),
        (value("release", "Cobalt-Latch release violet", replaces="T1:release"),),
        correction="T1",
        scope=("D3.manual",),
    )
    add(
        "D3",
        1,
        "Return to the D3-task latch test: which alignment applies?",
        [old, noise1, noise2],
        categories=("topic return", "old-but-relevant"),
        relation="return",
        facts=(("entity", "Cobalt-Latch release amber", "T1"),),
        groups=((("T1",), True),),
        irrelevant=("T2", "T3"),
        reference="Return to accepted amber intent: A may use active bounded State without raw T1; AB0 may recover T1 through B. Answer three-notch alignment from current Evidence; do not inherit display topic.",
        aspects=("release amber", "three-notch alignment"),
        support=("D3.manual", "Cobalt-Latch release amber uses a three-notch alignment."),
        limits={
            "cp-r-v1": "old raw source unavailable",
            "cp-a-v1": "Active bounded semantic State resolves latch/release intent; no old raw text/coverage/B credit",
        },
    )
    add(
        "D3",
        2,
        "Return to the D3-task latch test: which alignment applies?",
        [old, noise1, noise2, correction],
        categories=("user correction", "constraint supersession", "topic return"),
        relation="return",
        facts=(("entity", "Cobalt-Latch release violet", "T4"),),
        groups=((("T1", "T4"), True),),
        irrelevant=("T2", "T3"),
        reference="Recover complete T1/T4 correction group; retain amber record as superseded, use violet and five-notch alignment.",
        aspects=("release violet", "five-notch alignment"),
        support=("D3.manual", "Cobalt-Latch release violet uses a five-notch alignment."),
        limits={
            "cp-r-v1": "incomplete_group/search_incomplete; never consume T4 partially",
            "cp-a-v1": "incomplete_group/search_incomplete despite current violet state",
        },
    )

    choices = prefix(
        "T1",
        "For D4-task valve comparison, consider Beacon-North and Beacon-South equally.",
        "D4-task",
        ("Beacon-North", "Beacon-South"),
        (value("north", "Beacon-North"), value("south", "Beacon-South")),
        scope=("D4.manual",),
    )
    ambiguous = prefix(
        "T2",
        "For the D4-task valve test, which indicator should it show?",
        "D4-task",
        state=(value("pending", "unresolved unit", "ambiguity"),),
        scope=("D4.manual",),
        control="clarification",
    )
    add(
        "D4",
        1,
        "For the D4-task valve test, which indicator should it show?",
        [choices],
        categories=("ambiguous reference",),
        dependency="unresolved",
        facts=(("entity", "Beacon-North", "T1"), ("entity", "Beacon-South", "T1")),
        groups=((("T1",), False),),
        outcome="clarification",
        reference="Ask which of North/South; choose neither; keep unresolved state; no documentary generation.",
    )
    add(
        "D4",
        2,
        "For the D4-task valve test, I mean Beacon-South: which indicator should it show?",
        [choices, ambiguous],
        categories=("ambiguous reference", "simple follow-up"),
        dependency="none",
        facts=(("entity", "Beacon-South", "CURRENT"),),
        groups=(),
        reference="Clear prior unresolved state for the explicit South choice; answer green indicator; do not use North's blue indicator.",
        aspects=("Beacon-South", "green indicator"),
        support=("D4.manual", "Beacon-South displays a green indicator after a valve test."),
    )

    quill = prefix(
        "T1",
        "For D5-task relay checks, assess Quill m4.",
        "D5-task",
        ("Quill m4",),
        (value("unit", "Quill m4"),),
        scope=("D5.manual",),
    )
    for n, q in (
        (1, "For the D5-task relay check, before 24 hours must it relay?"),
        (2, "For the D5-task relay check, before 24 hours must it NOT relay?"),
    ):
        add(
            "D5",
            n,
            q,
            [quill],
            categories=("rewrite-required", "rewrite-danger / negation"),
            facts=(("entity", "Quill m4", "T1"),),
            groups=((("T1",), False),),
            protected=(("time", "24 hours"),) if n == 1 else (("time", "24 hours"), ("negation", "NOT")),
            reference="Preserve time/negation and Quill m4 identity; relay before 24 hours is prohibited. V1 answer no; V2 answer yes to NOT relaying.",
            aspects=("Quill m4", "relay before 24 hours prohibited"),
            support=(
                "D5.manual",
                "Quill m4 must not relay before 24 hours have elapsed after initialization.",
            ),
        )

    old = prefix(
        "T1",
        "Keep Sable-Pump maintenance discussion separate from contingency questions.",
        "maintenance",
        scope=("D6.ledger", "D6.contingency"),
    )
    for n, scope in ((1, ["D6.ledger", "D6.contingency"]), (2, ["D6.ledger"])):
        add(
            "D6",
            n,
            "During a brownout, what contingency must Sable-Pump apply?",
            [old],
            categories=("long conversation / context pressure", "document-scope change")
            if n == 1
            else ("document-scope change", "evidence-insufficient"),
            dependency="none",
            relation="shift",
            scope=scope,
            irrelevant=("T1",),
            outcome="documentary_answer" if n == 1 else "evidence_insufficient",
            reference="Use gravity bypass from current contingency source; full-pack L−1/L/L+1 capacity tests are separate L1 fixtures."
            if n == 1
            else "Report evidence insufficient in ledger-only scope; never reuse excluded contingency or historical answers; capacity refusal is distinct.",
            aspects=("gravity bypass",) if n == 1 else (),
            support=("D6.contingency", "During a brownout, Sable-Pump must switch to the gravity bypass.")
            if n == 1
            else None,
        )

    manifest = dict(
        schema_revision="v02a-multiturn-dev-v3",
        dataset_id=DATASET_ID,
        version=3,
        predecessor=dict(
            dataset_id="citeweave-v02a-development-v2",
            sha256="3b1ef5dc37376cf26b5fb20aa8367d76ed2af5ccf376a312a62fc2d6dbcd20a7",
            owner_decision="D1_V2_TOPIC_RETURN_CLARIFIED",
        ),
        split="Development",
        owner_review="PENDING",
        sealed_content="ABSENT_INACCESSIBLE",
        author="CiteWeave project original AI-assisted proposals, 2026-10-01; not Human Gold",
        license="MIT",
        protocol_sha256=hashlib.sha256((ROOT / "docs/V02_COMPARISON_PROTOCOL.md").read_bytes()).hexdigest(),
        clarification_revision="owner-topic-focus-return-20261001",
        seed=20260929,
        repeat=1,
        sources=sources,
        views=views,
        category_coverage={c: [v["id"] for v in views if c in v["categories"]] for c in CATEGORIES},
        connectivity_review="OWNER_PENDING_NO_CAL_OR_G_REUSE",
        closed_loop_branch=dict(
            first="D4.V1",
            required_kind="clarification",
            next="D4.V2",
            reply="For the D4-task valve test, I mean Beacon-South: which indicator should it show?",
            label_review="PENDING",
            mode="L1_CLOSED_LOOP_SEPARATE_FROM_FIXED_PREFIX",
        ),
    )
    from citeweave.evaluation.dev_dataset import DevManifest

    raw = canonical(DevManifest.model_validate(manifest).model_dump(mode="json"))
    # New proposal only: never rewrite a predecessor or existing different bytes.
    import json

    from citeweave.evaluation.dev_dataset import V2_DATASET_HASH

    old_raw = (ROOT / "evals/citeweave-v02a-development-v2.json").read_bytes()
    if hashlib.sha256(old_raw).hexdigest() != V2_DATASET_HASH:
        raise ValueError("dev_predecessor_hash_mismatch")
    old = json.loads(old_raw)
    if manifest["sources"] != old["sources"]:
        raise ValueError("dev_unrequested_source_change")
    for current, previous in zip(manifest["views"], old["views"], strict=True):
        allowed = (
            {"topic_relation", "reference", "assertions", "sha256"} if current["id"] == "D1.V2" else set()
        )
        if any(current[k] != previous[k] for k in current if k not in allowed):
            raise ValueError("dev_unrequested_view_change")
    target = ROOT / "evals" / (DATASET_ID + ".json")
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError("dev_immutable_proposal_exists")
    else:
        with target.open("xb") as stream:
            stream.write(raw)
    print("DEV proposal bytes SHA256", hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    main()
