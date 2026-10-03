"""One finite DEV campaign, serialized PG reservations and evaluation settlement.

No provider construction or I/O. SYNTHETIC policies can exercise the ledger but
can NEVER construct a provider. Disabled policy is the sole preparation default.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4, uuid5

from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import func, select, text

from citeweave.conversation_contract import CoreConflict, DurableDTO
from citeweave.costs import RATE_CARD, maximum_cost
from citeweave.db import transaction
from citeweave.domain import EvalCaseRow, EvalRunRow, ProviderPhaseRow
from citeweave.evaluation.dev_approval import APPROVAL_ID, APPROVAL_SHA256
from citeweave.evaluation.dev_campaign_models import DevCampaignRow
from citeweave.evaluation.dev_dataset import DATASET_HASH, DATASET_ID, digest
from citeweave.provider_accounting import ACCOUNTING_REVISION, request_hash


class Limits(DurableDTO):
    calls: int = Field(ge=0, strict=True)
    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)
    total_tokens: int = Field(ge=0, strict=True)
    yuan: Decimal = Field(ge=0, allow_inf_nan=False, max_digits=12, decimal_places=8)


class Slot(DurableDTO):
    case: str
    purpose: Literal["interpretation", "generation"]
    input_tokens: int = Field(gt=0, strict=True)
    output_tokens: int = Field(gt=0, strict=True)


class DevPolicy(DurableDTO):
    campaign_id: UUID
    name: str
    mode: Literal["DISABLED", "SYNTHETIC", "HUMAN"] = "DISABLED"
    dataset_id: Literal["citeweave-v02a-development-v3"] = DATASET_ID
    dataset_sha256: Literal["a01953930e2893065dc6f724b6ce896015124744d6614ac14a6354f087636023"] = DATASET_HASH
    approval_id: Literal["citeweave-v02a-development-v3-human-gold-20261001"] = APPROVAL_ID
    approval_sha256: Literal["df55c120f92ee4998083872cb6bea421101fc1c9eb89c3dd730242b064debd66"] = (
        APPROVAL_SHA256
    )
    identities: dict[str, str]
    slots: tuple[Slot, ...]
    cases: tuple[str, ...]
    proposed: Limits
    grant: Limits
    authorization_id: UUID | None = None
    schema_acceptance_id: UUID | None = None
    schema_accepted_at: AwareDatetime | None = None
    account_confirmed_at: AwareDatetime | None = None
    account_checks: dict[str, bool] = Field(default_factory=dict)
    expires_at: AwareDatetime
    deadline: AwareDatetime
    review_minutes: int = Field(gt=0, strict=True)
    review_units: Literal[36] = 36

    @model_validator(mode="after")
    def frozen(self):
        expected_cases = {
            f"D{i}.V{j}:{a}" for i in range(1, 7) for j in (1, 2) for a in ("cp-a-v1", "cp-ab0-v1")
        }
        if set(self.cases) != expected_cases or len(self.cases) != 24 or len(self.slots) > 38:
            raise ValueError("dev_population_invalid")
        if len({(s.case, s.purpose) for s in self.slots}) != len(self.slots):
            raise ValueError("dev_slot_duplicate")
        if any(s.case not in self.cases for s in self.slots):
            raise ValueError("dev_slot_case_invalid")
        # This restriction applies even to a separately signed HUMAN policy.
        # Missing slots may never be reassigned to another stage/view/repeat.
        from types import SimpleNamespace

        from citeweave.evaluation.dev_dispatch import slots_for_view

        if (
            any(
                s.purpose
                not in slots_for_view(SimpleNamespace(id=s.case.split(":")[0]), s.case.split(":")[1])
                for s in self.slots
            )
            or self.proposed.calls > 38
        ):
            raise ValueError("dev_conditional_slot_not_allowed")
        if self.mode != "HUMAN" and self.grant != Limits(
            calls=0, input_tokens=0, output_tokens=0, total_tokens=0, yuan=0
        ):
            raise ValueError("dev_nonhuman_grant_must_be_zero")
        if self.mode == "HUMAN" and (
            not self.authorization_id
            or not self.schema_acceptance_id
            or not self.schema_accepted_at
            or not self.account_confirmed_at
            or set(self.account_checks)
            != {"endpoint", "CNY", "rates", "alias", "private_funds", "monthly_budget"}
            or not all(self.account_checks.values())
            or any(
                getattr(self.grant, k) > getattr(self.proposed, k)
                for k in ("calls", "input_tokens", "output_tokens", "total_tokens", "yuan")
            )
        ):
            raise ValueError("dev_human_authorization_incomplete")
        required = {
            "commit",
            "tree",
            "config",
            "prompts",
            "provider",
            "tokenizer",
            "rate",
            "index",
            "protocol",
        }
        if not required <= self.identities.keys():
            raise ValueError("dev_identity_incomplete")
        return self


def create(workspace, kb, policy):
    policy = DevPolicy.model_validate(policy.model_dump())
    value = policy.model_dump(mode="json")
    with transaction() as db:
        # Global creation lock only; phase work locks one campaign row.
        db.execute(text("SELECT pg_advisory_xact_lock(606012)"))
        existing = db.get(DevCampaignRow, policy.campaign_id)
        if existing:
            if existing.policy != value:
                raise CoreConflict("dev_policy_identity_conflict")
            return existing.id
        now = db.scalar(select(func.clock_timestamp()))
        if not now < policy.expires_at <= policy.deadline or policy.deadline > now + timedelta(minutes=153):
            raise CoreConflict("dev_policy_deadline_invalid")
        db.add(
            EvalRunRow(
                id=policy.campaign_id,
                workspace_id=workspace,
                kb_id=kb,
                key=policy.name,
                dataset_id=DATASET_ID,
                dataset_hash=DATASET_HASH,
                split="Development",
                status="DEV_DISABLED" if policy.mode == "DISABLED" else "DEV_ACTIVE",
                versions={},
                runtime_config={"identities": policy.identities},
                runtime_policy="dev-bounded-campaign-v1",
                total_deadline=policy.deadline,
            )
        )
        db.flush()
        db.add(
            DevCampaignRow(
                id=policy.campaign_id,
                policy=value,
                policy_sha256=digest(value),
                status={"HUMAN": "ACTIVE", "SYNTHETIC": "SYNTHETIC", "DISABLED": "DISABLED"}[policy.mode],
                expires_at=policy.expires_at,
                deadline=policy.deadline,
            )
        )
        db.flush()  # Establish DEV ownership before the case INSERT triggers run.
        for key in policy.cases:
            db.add(EvalCaseRow(eval_run_id=policy.campaign_id, case_id=key, max_attempts=1))
    return policy.campaign_id


def _lock(db, campaign_id, workspace):
    db.execute(text("SELECT set_config('lock_timeout','1000',true)"))
    db.execute(text("SELECT set_config('statement_timeout','1000',true)"))
    row = db.scalar(select(DevCampaignRow).where(DevCampaignRow.id == campaign_id).with_for_update())
    if not row or db.get(EvalRunRow, campaign_id).workspace_id != workspace:
        raise CoreConflict("dev_campaign_not_authorized")
    policy = DevPolicy.model_validate(row.policy)
    if digest(row.policy) != row.policy_sha256:
        raise CoreConflict("dev_policy_hash_mismatch")
    return row, policy, db.scalar(select(func.clock_timestamp()))


def _phases(db, campaign_id):
    return list(db.scalars(select(ProviderPhaseRow).where(ProviderPhaseRow.eval_run_id == campaign_id)))


def _stop(db, row, reason):
    if row.status not in {"DISABLED", "COMPLETE"}:
        row.status, row.stop_reason = "STOPPED", reason
        run = db.get(EvalRunRow, row.id)
        run.status = "INCONCLUSIVE"


def _unknown_case(db, row, key, now):
    case = db.get(EvalCaseRow, (row.id, key))
    if case and case.status == "RUNNING":
        case.status, case.completed_at = "OUTCOME_UNKNOWN", now
        case.result = dict(
            **{k: v for k, v in (case.result or {}).items() if k in {"request_evidence", "target_context"}},
            publication="EVALUATION_ONLY_NOT_PRODUCT_ACCEPTED",
            outcome="UNKNOWN",
        )


def _check(db, row, policy, now, case=None):
    # Return a failure, commit STOPPED, then raise outside transaction.
    phases = _phases(db, row.id)
    if any(
        p.state == "UNKNOWN" or p.state == "DISPATCHED" and p.authorization_deadline <= now for p in phases
    ):
        for phase in phases:
            if phase.state == "DISPATCHED" and phase.authorization_deadline <= now:
                phase.state, phase.outcome = "UNKNOWN", "unknown"
                _unknown_case(db, row, phase.case_id, now)
        _stop(db, row, "UNKNOWN")
        return "dev_campaign_unknown"
    if row.status not in {"ACTIVE", "SYNTHETIC"}:
        return "dev_campaign_disabled_or_stopped"
    if now >= min(row.expires_at, row.deadline):
        _stop(db, row, "deadline")
        return "dev_campaign_deadline"
    if case and (case.status != "RUNNING" or row.active_case != case.case_id or now >= case.active_deadline):
        _stop(db, row, "target_deadline_or_ownership")
        return "dev_target_not_active"
    minutes = sum(v["minutes"] for v in row.review.values())
    if minutes >= policy.review_minutes or len(row.review) >= policy.review_units:
        _stop(db, row, "review_capacity")
        return "dev_review_capacity"
    return None


def begin(workspace, campaign_id, key):
    failure, result = None, None
    with transaction() as db:
        row, policy, now = _lock(db, campaign_id, workspace)
        case = db.get(EvalCaseRow, (campaign_id, key))
        if not case:
            raise CoreConflict("dev_case_not_allowed")
        if case.status in {"COMPLETED", "FAILED", "OUTCOME_UNKNOWN"}:
            return dict(recovered=True, status=case.status, result=case.result)
        failure = _check(db, row, policy, now)
        if not failure:
            if row.active_case or case.execution_attempt:
                raise CoreConflict("dev_no_retry_or_parallel_target")
            row.active_case = key
            case.status, case.owner, case.fence, case.execution_attempt = "RUNNING", uuid4(), 1, 1
            case.started_at = now
            case.active_deadline = min(now + timedelta(seconds=45), row.deadline, row.expires_at)
            result = dict(recovered=False, owner=case.owner, fence=case.fence, deadline=case.active_deadline)
    if failure:
        raise CoreConflict(failure)
    return result


def _budget(phases, limits, candidate=None):
    values = phases + ([candidate] if candidate else [])
    inputs, outputs = sum(p.input_tokens for p in values), sum(p.output_tokens for p in values)
    amount = sum((p.reserved_yuan for p in values), Decimal(0))
    if (
        len(values) > limits.calls
        or inputs > limits.input_tokens
        or outputs > limits.output_tokens
        or inputs + outputs > limits.total_tokens
        or amount > limits.yuan
    ):
        raise CoreConflict("dev_campaign_budget_exceeded")


def prepare(workspace, campaign_id, key, owner, purpose, body, accounting):
    measured = accounting.measure(body)  # Exact full reserialization, before any phase mutation.
    failure, phase_id = None, None
    with transaction() as db:
        row, policy, now = _lock(db, campaign_id, workspace)
        case = db.get(EvalCaseRow, (campaign_id, key))
        failure = _check(db, row, policy, now, case)
        if not failure:
            if not case or case.owner != owner:
                raise CoreConflict("dev_target_owner_conflict")
            slot = next((s for s in policy.slots if s.case == key and s.purpose == purpose), None)
            if (
                not slot
                or measured["input_tokens"] > slot.input_tokens
                or body["max_tokens"] != slot.output_tokens
            ):
                raise CoreConflict("dev_request_bound_exceeded")
            phases = _phases(db, campaign_id)
            logical = "dev:" + str(campaign_id) + ":" + key + ":" + purpose
            if any(p.logical_key == logical for p in phases):
                raise CoreConflict("dev_phase_already_reserved_no_redispatch")
            if any(p.state in {"UNKNOWN", "DISPATCHED"} for p in phases):
                raise CoreConflict("dev_previous_phase_unsettled")
            phase = ProviderPhaseRow(
                id=uuid4(),
                eval_run_id=campaign_id,
                case_id=key,
                owner=owner,
                fence=case.fence,
                logical_key=logical,
                phase=purpose,
                phase_attempt=1,
                state="PREPARED",
                provider="deepseek",
                model=body["model"],
                price_revision=RATE_CARD,
                authorization_id=uuid5(campaign_id, key + ":" + purpose),
                authorization_deadline=case.active_deadline,
                reserved_at=now,
                request_hash=request_hash(body),
                prompt_revision=ACCOUNTING_REVISION,
                input_tokens=slot.input_tokens
                if policy.identities.get("semantic_contract")
                else measured["input_tokens"],
                output_tokens=slot.output_tokens,
                reserved_yuan=maximum_cost(
                    slot.input_tokens
                    if policy.identities.get("semantic_contract")
                    else measured["input_tokens"],
                    slot.output_tokens,
                ),
            )
            _budget(phases, policy.proposed if policy.mode == "SYNTHETIC" else policy.grant, phase)
            reservation = db.begin_nested()
            db.add(phase)
            db.flush()
            checked_at = db.scalar(select(func.clock_timestamp()))
            failure = _check(db, row, policy, checked_at, case)
            if failure:
                # A failed, never-committed INSERT is rolled back, not DELETEd.
                # Reapply the durable stop outside the rolled-back savepoint.
                reservation.rollback()
                failure = _check(db, row, policy, checked_at, case)
            else:
                reservation.commit()
                phase_id = phase.id
    if failure:
        raise CoreConflict(failure)
    return phase_id


def dispatch(
    workspace, campaign_id, key, owner, phase_id, body, accounting, identities, *, real_transport=False
):
    # Recount immediately at the durable DISPATCHED boundary as well as prepare.
    measured = accounting.measure(body)
    failure = None
    with transaction() as db:
        row, policy, now = _lock(db, campaign_id, workspace)
        case = db.get(EvalCaseRow, (campaign_id, key))
        failure = _check(db, row, policy, now, case)
        if not failure:
            if real_transport and (
                policy.mode != "HUMAN"
                or row.status != "ACTIVE"
                or policy.grant.calls == 0
                or policy.grant.yuan == 0
            ):
                raise CoreConflict("dev_durable_human_authorization_required")
            phase = db.get(ProviderPhaseRow, phase_id)
            slot = (
                next((s for s in policy.slots if s.case == key and s.purpose == phase.phase), None)
                if phase
                else None
            )
            if (
                not phase
                or phase.eval_run_id != campaign_id
                or phase.case_id != key
                or phase.owner != owner
                or case.owner != owner
                or phase.state != "PREPARED"
                or phase.dispatched_at is not None
                or phase.request_hash != request_hash(body)
                or phase.input_tokens
                != (
                    slot.input_tokens
                    if slot and policy.identities.get("semantic_contract")
                    else measured["input_tokens"]
                )
                or measured["input_tokens"] > phase.input_tokens
                or policy.identities != identities
            ):
                raise CoreConflict("dev_dispatch_identity_or_no_redispatch")
            if policy.identities.get("semantic_contract"):
                recorded = (case.result or {}).get("request_evidence", {}).get(phase.phase)
                if (
                    not recorded
                    or recorded["phase_id"] != str(phase_id)
                    or recorded["identities"] != policy.identities
                    or recorded["measurement"] != measured
                ):
                    raise CoreConflict("dev_dispatch_request_evidence_missing_or_drift")
            _budget(_phases(db, campaign_id), policy.proposed if policy.mode == "SYNTHETIC" else policy.grant)
            phase.state, phase.outcome, phase.dispatched_at = "DISPATCHED", "unknown", now
            db.flush()
            failure = _check(db, row, policy, db.scalar(select(func.clock_timestamp())), case)
            if failure:
                phase.state, phase.outcome = "UNKNOWN", "unknown"
                _stop(db, row, "UNKNOWN")
    if failure:
        raise CoreConflict(failure)


def record_request(workspace, campaign_id, key, owner, phase_id, evidence):
    """Bind semantic/wire evidence durably before DISPATCHED; existing JSON only."""
    with transaction() as db:
        row, policy, now = _lock(db, campaign_id, workspace)
        case = db.get(EvalCaseRow, (campaign_id, key))
        failure = _check(db, row, policy, now, case)
        if failure:
            raise CoreConflict(failure)
        phase = db.get(ProviderPhaseRow, phase_id)
        if (
            not phase
            or phase.eval_run_id != campaign_id
            or phase.case_id != key
            or phase.owner != owner
            or case.owner != owner
            or phase.state != "PREPARED"
            or evidence["campaign_id"] != str(campaign_id)
            or evidence["measurement"]["request_hash"] != phase.request_hash
            or evidence["measurement"]["input_tokens"] > phase.input_tokens
            or (
                not policy.identities.get("semantic_contract")
                and evidence["measurement"]["input_tokens"] != phase.input_tokens
            )
            or evidence["measurement"]["output_tokens"] != phase.output_tokens
        ):
            raise CoreConflict("dev_request_evidence_identity_conflict")
        prior = (case.result or {}).get("request_evidence", {})
        if phase.phase in prior:
            raise CoreConflict("dev_request_evidence_already_recorded")
        case.result = {
            **(case.result or {}),
            "request_evidence": {
                **prior,
                phase.phase: {
                    **evidence,
                    "phase_id": str(phase_id),
                    "rate": RATE_CARD,
                    "reservation_input_cap": phase.input_tokens,
                    "reservation_output_cap": phase.output_tokens,
                    "identities": policy.identities,
                },
            },
        }


def record_context(workspace, campaign_id, key, owner, context):
    """Keep actual History/State/B attribution even if the provider becomes UNKNOWN."""
    failure = None
    with transaction() as db:
        row, policy, now = _lock(db, campaign_id, workspace)
        case = db.get(EvalCaseRow, (campaign_id, key))
        failure = _check(db, row, policy, now, case)
        if not failure:
            if not case or case.owner != owner or "target_context" in (case.result or {}):
                raise CoreConflict("dev_target_context_identity_conflict")
            case.result = {**(case.result or {}), "target_context": context}
    if failure:
        raise CoreConflict(failure)


def observe(workspace, campaign_id, key, owner, phase_id, observation, *, known, output=None):
    from citeweave.conversation_provider import Observation, _observation

    receipt = Observation.model_validate(observation)
    with transaction() as db:
        row, _, now = _lock(db, campaign_id, workspace)
        phase = db.get(ProviderPhaseRow, phase_id)
        if (
            not phase
            or phase.eval_run_id != campaign_id
            or phase.case_id != key
            or phase.owner != owner
            or phase.state != "DISPATCHED"
        ):
            raise CoreConflict("dev_phase_observation_conflict")
        _observation(phase, receipt)
        phase.state, phase.outcome = (
            ("COMPLETED", "known") if known and receipt.result_hash else ("UNKNOWN", "unknown")
        )
        if phase.state == "UNKNOWN":
            _unknown_case(db, row, key, now)
            _stop(db, row, "UNKNOWN")
        if output is not None:
            import hashlib

            if (
                phase.state != "COMPLETED"
                or hashlib.sha256(output.encode()).hexdigest() != receipt.result_hash
            ):
                raise CoreConflict("dev_known_output_identity_conflict")
            case = db.get(EvalCaseRow, (campaign_id, key))
            if case.status != "RUNNING":
                raise CoreConflict("dev_output_target_terminal")
            case.result = {
                **(case.result or {}),
                "provider_outputs": {**(case.result or {}).get("provider_outputs", {}), phase.phase: output},
            }
        if receipt.usage and (
            (receipt.usage.prompt_tokens or 0) > phase.input_tokens
            or (receipt.usage.completion_tokens or 0) > phase.output_tokens
        ):
            _stop(db, row, "provider_usage_over_budget")


def settle(workspace, campaign_id, key, owner, result, *, failed=False):
    """Evaluation terminal only: no product Run/Acceptance/head mutation."""
    if key in {"D1.V2:cp-a-v1", "D3.V1:cp-a-v1"} and result.get("product_acceptance") is not None:
        raise CoreConflict("dev_state_only_cannot_publish_product_acceptance")
    failure = None
    with transaction() as db:
        row, policy, now = _lock(db, campaign_id, workspace)
        case = db.get(EvalCaseRow, (campaign_id, key))
        if not case:
            raise CoreConflict("dev_case_not_allowed")
        if case.status in {"COMPLETED", "FAILED"}:
            if case.result.get("result_sha256") != digest(result):
                raise CoreConflict("dev_settlement_identity_conflict")
            return case.result
        if not case or case.owner != owner or case.status != "RUNNING" or row.active_case != key:
            raise CoreConflict("dev_target_owner_conflict")
        phases = [p for p in _phases(db, campaign_id) if p.case_id == key]
        if now >= min(case.active_deadline, row.expires_at, row.deadline):
            _stop(db, row, "deadline")
        # Known provider completion remains known after cancellation/deadline.
        # This closes only its evaluation receipt and cannot allow another send.
        failure = (
            None
            if phases and all(p.state == "COMPLETED" for p in phases)
            else _check(db, row, policy, now, case)
        )
        if not failure:
            if case.owner != owner:
                raise CoreConflict("dev_target_owner_conflict")
            phases = [p for p in _phases(db, campaign_id) if p.case_id == key]
            if any(p.state != "COMPLETED" for p in phases):
                raise CoreConflict("dev_settlement_provider_not_known")
            case.status = "FAILED" if failed else "COMPLETED"
            case.completed_at = now
            case.result = dict(
                **{
                    k: v
                    for k, v in (case.result or {}).items()
                    if k in {"request_evidence", "provider_outputs", "target_context"}
                },
                publication="PRODUCT_ACCEPTED"
                if result.get("product_acceptance")
                else "EVALUATION_ONLY_NOT_PRODUCT_ACCEPTED",
                result=result,
                result_sha256=digest(result),
                phase_ids=[str(p.id) for p in phases],
            )
            row.active_case = None
            value = case.result
    if failure:
        raise CoreConflict(failure)
    return value


def cancel(workspace, campaign_id):
    with transaction() as db:
        row, _, _ = _lock(db, campaign_id, workspace)
        _stop(db, row, "cancelled")


def close_execution(workspace, campaign_id):
    """All exact targets settled; prohibit spending while Human reviews proceed."""
    with transaction() as db:
        row, policy, _ = _lock(db, campaign_id, workspace)
        if row.status not in {"ACTIVE", "SYNTHETIC", "COMPLETE"}:
            raise CoreConflict("dev_campaign_not_complete")
        cases = [db.get(EvalCaseRow, (campaign_id, key)) for key in policy.cases]
        if row.active_case or any(c.status not in {"COMPLETED", "FAILED"} for c in cases):
            raise CoreConflict("dev_campaign_not_complete")
        if any(p.state != "COMPLETED" for p in _phases(db, campaign_id)):
            raise CoreConflict("dev_campaign_provider_not_known")
        row.status = "COMPLETE"
        db.get(EvalRunRow, campaign_id).status = "DEV_REVIEW_PENDING"


def complete_review(workspace, campaign_id):
    with transaction() as db:
        row, policy, _ = _lock(db, campaign_id, workspace)
        if row.status != "COMPLETE" or not {"OUTPUT:" + k for k in policy.cases} <= row.review.keys():
            raise CoreConflict("dev_mandatory_output_reviews_incomplete")
        # No automatic quality/winner/promotion decision. Minutes are prospective
        # actuals; this does not assign historical unmeasured Gold minutes.
        db.get(EvalRunRow, campaign_id).status = "DEV_REVIEWED_NOT_PROMOTED"


def record_review(workspace, campaign_id, unit, receipt_hash, minutes, *, reviewer, decision):
    if type(minutes) is not int or minutes < 0:
        raise ValueError("dev_review_actual_minutes_required")
    with transaction() as db:
        row, policy, now = _lock(db, campaign_id, workspace)
        allowed = {"OUTPUT:" + case for case in policy.cases} | {
            f"DISPUTE:D{i}.V{j}" for i in range(1, 7) for j in (1, 2)
        }
        if unit not in allowed or unit in row.review:
            raise CoreConflict("dev_review_unit_invalid")
        if (
            len(row.review) + 1 > 36
            or sum(v["minutes"] for v in row.review.values()) + minutes > policy.review_minutes
        ):
            raise CoreConflict("dev_review_capacity")
        if not reviewer or decision not in {"APPROVE", "REVISE", "DISPUTED"} or len(receipt_hash) != 64:
            raise CoreConflict("dev_review_confirmation_required")
        row.review = {
            **row.review,
            unit: dict(
                receipt_sha256=receipt_hash,
                minutes=minutes,
                reviewer=reviewer,
                decision=decision,
                recorded_at=now.isoformat(),
            ),
        }
