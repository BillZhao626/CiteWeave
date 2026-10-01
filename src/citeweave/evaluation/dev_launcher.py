"""One separately HUMAN-authorized campaign; no CLI/default positive authority.

Real adapters are constructed here, with no injectable fixture repository or
provider factory. Preparation and SYNTHETIC markers never enter this path.
"""

import asyncio
import hashlib
import json
import subprocess
from contextlib import aclosing
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid5

from pydantic import ValidationError

from citeweave.answering import REFUSAL, validate_citations
from citeweave.conversation_contract import Admission, CoreConflict
from citeweave.conversation_evidence import assemble, make_result
from citeweave.conversation_evidence_pg import StructuralEvidenceRetriever
from citeweave.conversation_interpretation import InterpretationDraft, interpret
from citeweave.conversation_provider import Observation
from citeweave.conversation_runtime import generation_messages
from citeweave.costs import RATE_CARD
from citeweave.db import transaction
from citeweave.domain import IndexRow, VersionRow
from citeweave.evaluation import dev_campaign as campaign
from citeweave.evaluation.dev_approval import load_human_gold
from citeweave.evaluation.dev_arms import arm
from citeweave.evaluation.dev_dataset import digest, identity, verify_original_sources
from citeweave.evaluation.dev_dispatch import decode_output, request_contract, slots_for_view
from citeweave.evaluation.dev_environment import bind_environment, model_binding, verify_environment
from citeweave.evaluation.dev_execution import frozen_runtime
from citeweave.evaluation.dev_real import RealDevBackend, context_for
from citeweave.evaluation.dev_state import evaluation_messages, state_intent
from citeweave.llm import DeepSeekProvider
from citeweave.model_client import ModelGateway
from citeweave.provider_accounting import TOKENIZER_SHA256, DeepSeekAccounting
from citeweave.schemas import Answer
from citeweave.settings import ROOT, settings
from citeweave.trace import bounded_stage

CONTRACTS = ROOT / ".runtime/evaluation/v02-dev-paid-remediation/contracts-head0012.json"
ARMS = ("cp-a-v1", "cp-ab0-v1")


def code_identity():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    if git("status", "--porcelain"):
        raise CoreConflict("dev_candidate_worktree_dirty")
    return git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")


def live_identities(packet):
    commit, tree = code_identity()
    data, _, _ = load_human_gold(ROOT)
    verify_original_sources(ROOT, data)
    model_binding()
    with transaction() as db:
        for binding in packet["environment"]["bindings"]:
            from uuid import UUID

            version = db.get(VersionRow, UUID(binding["version_id"]))
            index = db.get(IndexRow, binding["index"])
            if (
                not version
                or not index
                or version.status != "READY"
                or index.state != "PUBLISHED"
                or version.index_collection != index.name
                or str(index.artifact_id) != binding["artifact_id"]
                or index.index_profile_hash != binding["index_profile_hash"]
                or index.embedding_identity != binding["embedding_identity"]
                or index.bm25_hash != binding["bm25_hash"]
            ):
                raise CoreConflict("dev_live_index_binding_drift")
    return dict(
        commit=commit,
        tree=tree,
        config=digest({"arms": {a: arm(a).config_hash for a in ARMS}, "runtime_files": frozen_runtime(ROOT)}),
        prompts=digest(
            {
                n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest()
                for n in (
                    "prompts/answer-telecom-v1.txt",
                    "prompts/conversation-interpretation-v1.txt",
                    "src/citeweave/evaluation/dev_state.py",
                )
            }
        ),
        provider="https://api.deepseek.com/chat/completions:deepseek-flash:non-thinking:one-send",
        tokenizer=TOKENIZER_SHA256,
        rate=RATE_CARD,
        index=packet["environment_sha256"],
        protocol=hashlib.sha256((ROOT / "docs/V02_COMPARISON_PROTOCOL.md").read_bytes()).hexdigest(),
    )


def require_human(policy):
    policy = campaign.DevPolicy.model_validate(policy.model_dump())
    if policy.mode != "HUMAN" or policy.grant.calls == 0 or policy.grant.yuan == 0:
        raise CoreConflict("dev_paid_human_authorization_required")
    return policy


class Calls:
    def __init__(self, workspace, policy, key, token, accounting, packet):
        self.policy = require_human(policy)  # Before any provider construction.
        self.workspace, self.key, self.token = workspace, key, token
        self.accounting, self.packet = accounting, packet

    def call(self, purpose, messages):
        slot = next((s for s in self.policy.slots if s.case == self.key and s.purpose == purpose), None)
        if not slot:
            raise CoreConflict("dev_phase_not_in_frozen_slots")
        body, _ = request_contract(purpose, messages, slot.input_tokens, slot.output_tokens, self.accounting)
        phase = campaign.prepare(
            self.workspace,
            self.policy.campaign_id,
            self.key,
            self.token["owner"],
            purpose,
            body,
            self.accounting,
        )

        def before_send():
            identities = live_identities(self.packet)
            if settings().deepseek_model != "deepseek-flash" or settings().provider_attempts != 1:
                raise CoreConflict("dev_provider_configuration_drift")
            campaign.dispatch(
                self.workspace,
                self.policy.campaign_id,
                self.key,
                self.token["owner"],
                phase,
                body,
                self.accounting,
                identities,
                real_transport=True,
            )
            if datetime.now(timezone.utc) >= self.token["deadline"]:
                raise CoreConflict("dev_postcommit_deadline")

        # The durable guard runs inside provider.before_send immediately before
        # the sole HTTPS POST. Attempts are never inherited from retry defaults.
        provider = DeepSeekProvider()
        provider.max_attempts = 1
        text_parts, observation = [], {}

        async def consume():
            remaining = (self.token["deadline"] - datetime.now(timezone.utc)).total_seconds()
            async with asyncio.timeout(max(0, min(35, remaining))):
                async with aclosing(provider.stream_request(body, before_send=before_send)) as stream:
                    async for part in stream:
                        if part.get("text"):
                            text_parts.append(part["text"])
                        # Same mapping as the production conversation adapter:
                        # stream id -> receipt request_id; served-model metadata
                        # is diagnostic, not the immutable reserved model alias.
                        if part.get("usage") is not None:
                            observation["usage"] = part["usage"]
                        if part.get("provider_id") is not None:
                            observation["request_id"] = part["provider_id"]
                        if sum(len(v.encode()) for v in text_parts) > slot.output_tokens * 128:
                            raise CoreConflict("dev_stream_output_bytes_exceeded")

        try:
            asyncio.run(consume())
            raw = "".join(text_parts)
            observation["result_hash"] = hashlib.sha256(raw.encode()).hexdigest()
            campaign.observe(
                self.workspace,
                self.policy.campaign_id,
                self.key,
                self.token["owner"],
                phase,
                observation,
                known=True,
                output=raw,
            )
        except BaseException:
            # May fail before send: only a durable DISPATCHED phase is UNKNOWN.
            from citeweave.domain import ProviderPhaseRow

            with transaction() as db:
                dispatched = db.get(ProviderPhaseRow, phase).state == "DISPATCHED"
            if dispatched:
                # An unsupported receipt cannot be accepted or reused to retry.
                # Keep its reservation UNKNOWN without coercing invalid usage.
                try:
                    Observation.model_validate(observation)
                except ValidationError:
                    observation = {}
                campaign.observe(
                    self.workspace,
                    self.policy.campaign_id,
                    self.key,
                    self.token["owner"],
                    phase,
                    observation,
                    known=False,
                )
            campaign.cancel(self.workspace, self.policy.campaign_id)
            raise
        # Invalid structured/answer output is known transport completion. Retain
        # its charge, fail the target, never attempt a JSON repair/provider retry.
        return decode_output(
            purpose, raw, finish_reason="stop", reserve=slot.output_tokens, accounting=self.accounting
        )


def launch(policy):
    """No default policy, no implicit grant, no fixture/provider injection."""
    policy = require_human(policy)
    data, _, _ = load_human_gold(ROOT)
    bind_environment()
    environment = verify_environment()  # Real PG/Qdrant and local E5/BGE/citations.
    packet = json.loads(CONTRACTS.read_bytes())
    if digest(environment) != packet["environment_sha256"]:
        raise CoreConflict("dev_frozen_environment_drift")
    if policy.identities != live_identities(packet):
        raise CoreConflict("dev_candidate_identity_drift")
    if [s.model_dump(mode="json") for s in policy.slots] != packet["slots"]:
        raise CoreConflict("dev_slot_contract_drift")
    planned = campaign.Limits(
        calls=packet["max_calls"],
        input_tokens=packet["input_tokens"],
        output_tokens=packet["output_tokens"],
        total_tokens=packet["total_tokens"],
        yuan=Decimal(packet["maximum_yuan"]),
    )
    if policy.proposed != planned:
        raise CoreConflict("dev_proposed_envelope_drift")
    campaign.create(identity("workspace"), identity("kb"), policy)
    accounting = DeepSeekAccounting(
        ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    )
    prompt = (ROOT / "prompts/answer-telecom-v1.txt").read_text(encoding="utf-8")
    receipts = []
    for view in data.views:
        for aid in ARMS:
            key = view.id + ":" + aid
            token = campaign.begin(identity("workspace"), policy.campaign_id, key)
            if token["recovered"]:
                receipts.append(token)
                if token["status"] == "OUTCOME_UNKNOWN":
                    raise CoreConflict("dev_campaign_unknown")
                continue
            backend = RealDevBackend(data, view, arm(aid), campaign_id=policy.campaign_id)
            run, result = None, None
            state_only = aid == "cp-a-v1" and view.id in {"D1.V2", "D3.V1"}
            try:
                with bounded_stage(max(0, (token["deadline"] - datetime.now(timezone.utc)).total_seconds())):
                    purposes = slots_for_view(view, aid)
                    if state_only or not purposes:
                        context = context_for(backend)
                    else:
                        request = Admission(
                            question=view.question,
                            scope=backend.scope(view.scope),
                            expected_head=backend.previous.id if backend.previous else None,
                        )
                        run = backend.begin(request)
                        context = context_for(backend, run=run, purpose="target")
                    if not purposes:
                        if context.history.failure != "incomplete_group":
                            raise CoreConflict("dev_zero_call_guard_drift")
                        result = {"guard": "incomplete_group", "calls": 0}
                    else:
                        calls = Calls(backend.workspace, policy, key, token, accounting, packet)
                        if "interpretation" in slots_for_view(view, aid):
                            draft = calls.call("interpretation", evaluation_messages(context))
                        else:
                            probe = next(
                                p for p in packet["probes"] if p["view"] == view.id and p["arm"] == aid
                            )
                            draft = InterpretationDraft.model_validate(probe["reviewed_independent_draft"])
                        decision = (
                            state_intent(context, draft) if state_only else interpret(context, draft=draft)
                        )
                        produced = decision.control_result
                        if decision.mode != "CLARIFY":
                            # These concrete production adapters cannot accept a
                            # FixtureRepository substituted through a parameter.
                            evidence = StructuralEvidenceRetriever(model=ModelGateway()).retrieve(
                                backend.workspace, context.request.scope, decision.selected_query
                            )
                            assembled = assemble(
                                backend.workspace,
                                run.id if run else uuid5(policy.campaign_id, key),
                                context,
                                decision,
                                evidence,
                                max_input_bytes=2**63 - 1,
                            )
                            raw = (
                                calls.call("generation", generation_messages(assembled, prompt))
                                if evidence.citations
                                else REFUSAL
                            )
                            answer = Answer(
                                run_id=assembled.run_id,
                                text=raw,
                                citations=validate_citations(raw, evidence.citations),
                                prompt_version="answer-telecom-v1",
                                estimated_yuan=None,
                            )
                            produced = make_result(assembled, answer)
                        result = dict(
                            state_only=state_only,
                            result=produced.model_dump(mode="json"),
                            interpretation=decision.model_dump(mode="json"),
                        )
                        if run:
                            result["product_acceptance"] = backend.accept(
                                run, context, produced, decision, draft
                            )
                receipts.append(
                    campaign.settle(backend.workspace, policy.campaign_id, key, token["owner"], result)
                )
            except BaseException as exc:
                # Known phases close FAILED, UNKNOWN retains its immutable receipt.
                # No automatic resume/retry/retrieval/provider repair is issued.
                terminal_error = None
                try:
                    campaign.settle(
                        backend.workspace,
                        policy.campaign_id,
                        key,
                        token["owner"],
                        {"error_type": type(exc).__name__},
                        failed=True,
                    )
                except CoreConflict as conflict:
                    terminal_error = conflict
                campaign.cancel(backend.workspace, policy.campaign_id)
                if run:
                    from citeweave import conversations as core
                    from citeweave.conversation_contract import RunStatus
                    from citeweave.domain import EvalCaseRow

                    with transaction() as db:
                        unknown = db.get(EvalCaseRow, (policy.campaign_id, key)).status == "OUTCOME_UNKNOWN"
                    core.finish(
                        backend.workspace,
                        backend.conversation,
                        run.turn_id,
                        run.id,
                        run.owner,
                        run.fence,
                        RunStatus.OUTCOME_UNKNOWN if unknown else RunStatus.FAILED,
                    )
                raise exc from terminal_error
    campaign.close_execution(identity("workspace"), policy.campaign_id)
    return receipts
