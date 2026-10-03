"""Freeze clean candidate identity and persist only a DISABLED zero grant."""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid5

from citeweave.evaluation.dev_campaign import DevPolicy, Limits, create
from citeweave.evaluation.dev_dataset import canonical, digest, identity
from citeweave.evaluation.dev_environment import bind_environment, verify_environment
from citeweave.evaluation.dev_launcher import CONTRACTS, live_identities


def main():
    bind_environment()
    contracts = json.loads(CONTRACTS.read_bytes())
    environment = verify_environment()
    if digest(environment) != contracts["environment_sha256"]:
        raise ValueError("dev_candidate_environment_drift")
    identities = live_identities(contracts)
    target = CONTRACTS.parent / "candidate.json"
    if target.exists():
        previous = json.loads(target.read_bytes())
        if previous["policy"]["identities"] != identities:
            raise ValueError("dev_candidate_receipt_immutable")
        print("Existing zero-authority candidate:", identities["commit"], identities["tree"])
        return
    now = datetime.now(timezone.utc)
    proposal = Limits(
        calls=contracts["max_calls"],
        input_tokens=contracts["input_tokens"],
        output_tokens=contracts["output_tokens"],
        total_tokens=contracts["total_tokens"],
        yuan=contracts["maximum_yuan"],
    )
    policy = DevPolicy(
        campaign_id=uuid5(identity("campaign"), identities["commit"] + ":paid-dev-disabled-v1"),
        name="dev-v3-disabled-" + identities["commit"][:16],
        identities=identities,
        mode="DISABLED",
        slots=contracts["slots"],
        cases=[f"D{i}.V{j}:{a}" for i in range(1, 7) for j in (1, 2) for a in ("cp-a-v1", "cp-ab0-v1")],
        proposed=proposal,
        grant=Limits(calls=0, input_tokens=0, output_tokens=0, total_tokens=0, yuan=0),
        expires_at=now + timedelta(minutes=153),
        deadline=now + timedelta(minutes=153),
        review_minutes=288,
        account_checks={
            k: False for k in ("endpoint", "CNY", "rates", "alias", "private_funds", "monthly_budget")
        },
    )
    create(identity("workspace"), identity("kb"), policy)
    target.write_bytes(
        canonical(
            dict(
                status="ZERO_AUTHORITY_CANDIDATE_NOT_HUMAN_GRANT",
                created_at=now.isoformat(),
                contract_sha256=digest(contracts),
                policy=policy.model_dump(mode="json"),
                external_calls=0,
                actual_yuan="0",
                historical_review_minutes="NOT_MEASURED",
                future_review=dict(output_units=24, dispute_units=12, total_units=36, minutes_ceiling=288),
                state_only_settlement="cw2_eval_cases+cw4_provider_phases+cw6_dev_campaigns/0012",
            )
        )
    )
    print("Zero-authority candidate:", identities["commit"], identities["tree"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Candidate freeze failed:", type(exc).__name__)
        raise SystemExit(1) from None
