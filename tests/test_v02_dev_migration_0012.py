"""Fresh populated 0011 -> revised 0012; direct SQL, zero real authority/I/O."""

import ast
import os
import re
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from pydantic import SecretStr
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from test_conversation_postgres import metadata
from test_v02_dev_campaign_postgres import BODY, KEY, Accounting, start

from citeweave.conversation_contract import CoreConflict
from citeweave.db import engine, migrate, transaction
from citeweave.domain import Base, EvalCaseRow, EvalRunRow, ProviderPhaseRow
from citeweave.evaluation import dev_campaign as campaign
from citeweave.evaluation.dev_campaign_models import DevCampaignRow
from citeweave.settings import ROOT, settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="requires isolated real PostgreSQL"),
]


def snapshot(table, predicate, **params):
    with transaction() as db:
        return db.scalar(text(f"SELECT to_jsonb(r) FROM {table} r WHERE {predicate}"), params)


@pytest.fixture(scope="module", autouse=True)
def fresh_0011():
    config = settings()
    original = config.database_url
    url = make_url(config.db_url())
    assert url.host in {"127.0.0.1", "localhost", "::1"}
    database = "cw_0012_revision_test_" + uuid4().hex
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text('CREATE DATABASE "' + database + '"'))
        created = True
        engine.cache_clear()
        config.database_url = SecretStr(url.set(database=database).render_as_string(hide_password=False))
        command.upgrade(cfg, "0011")
        with transaction() as db:
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0011"
        workspace, scope = metadata()
        run, phase = uuid4(), uuid4()
        with transaction() as db:
            db.add(
                EvalRunRow(
                    id=run,
                    workspace_id=workspace,
                    kb_id=scope.kb_id,
                    key=str(run),
                    dataset_id="original",
                    dataset_hash="0" * 64,
                    split="Development",
                    versions={},
                    runtime_config={},
                )
            )
            db.flush()
            db.add(EvalCaseRow(eval_run_id=run, case_id="legacy", max_attempts=3))
            db.flush()
            from sqlalchemy import MetaData, Table

            legacy_phase = Table("cw4_provider_phases", MetaData(), autoload_with=db.connection())
            db.execute(
                legacy_phase.insert().values(
                    id=phase,
                    eval_run_id=run,
                    case_id="legacy",
                    logical_key=str(phase),
                    phase="generation",
                    phase_attempt=2,
                    state="PREPARED",
                    outcome="not_dispatched",
                    owner=uuid4(),
                    fence=1,
                    reserved_at=db.scalar(select(func.clock_timestamp())),
                    reserved_yuan=Decimal("0.001"),
                )
            )
        before = (
            snapshot("cw2_eval_runs", "id=:id", id=run),
            snapshot("cw2_eval_cases", "eval_run_id=:id", id=run),
            snapshot("cw4_provider_phases", "id=:id", id=phase),
        )
        migrate()
        migrate()
        after = (
            snapshot("cw2_eval_runs", "id=:id", id=run),
            snapshot("cw2_eval_cases", "eval_run_id=:id", id=run),
            snapshot("cw4_provider_phases", "id=:id", id=phase),
        )
        assert all(
            all(current[key] == value for key, value in old.items())
            for old, current in zip(before, after, strict=True)
        )
        yield cfg, run, phase
    finally:
        if created:
            engine().dispose()
            engine.cache_clear()
            config.database_url = original
            with admin.connect() as connection:
                connection.execute(text('DROP DATABASE "' + database + '"'))
        admin.dispose()


def denied(sql, params, match="dev_"):
    with pytest.raises(IntegrityError, match=match), transaction() as db:
        db.execute(text(sql), params)


def prepared():
    w, p, token = start()
    phase = campaign.prepare(w, p.campaign_id, KEY, token["owner"], "generation", BODY, Accounting())
    return w, p, token, phase


def terminal(state):
    w, p, token, phase = prepared()
    if state != "REJECTED":
        campaign.dispatch(w, p.campaign_id, KEY, token["owner"], phase, BODY, Accounting(), p.identities)
        campaign.observe(
            w,
            p.campaign_id,
            KEY,
            token["owner"],
            phase,
            dict(result_hash="1" * 64, usage=dict(prompt_tokens=100, completion_tokens=40)),
            known=state == "COMPLETED",
        )
    else:
        with transaction() as db:
            db.execute(
                text(
                    "UPDATE cw4_provider_phases SET state='REJECTED', outcome='known_not_executed', "
                    "error_code='synthetic_rejection' WHERE id=:id"
                ),
                {"id": phase},
            )
    return w, p, token, phase


def test_fresh_head_repeat_and_unsupported_downgrade(fresh_0011):
    cfg, _, _ = fresh_0011
    with transaction() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0013"
    with pytest.raises(RuntimeError, match="use_fix_forward"):
        command.downgrade(cfg, "0011")
    with transaction() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0013"
        assert db.scalar(text("SELECT count(*) FROM cw2_eval_cases")) >= 1


def test_new_table_metadata_and_all_trigger_bodies():
    with engine().connect() as connection:
        ctx = MigrationContext.configure(
            connection,
            opts={
                "include_object": lambda obj, name, kind, reflected, compare_to: (
                    name == "cw6_dev_campaigns" if kind == "table" else True
                ),
                "compare_server_default": True,
            },
        )
        assert compare_metadata(ctx, Base.metadata) == []
        reflected = inspect(connection)
        columns = reflected.get_columns("cw6_dev_campaigns")
        declared = DevCampaignRow.__table__
        assert {c["name"] for c in columns} == set(declared.columns.keys())
        for c in columns:
            assert c["nullable"] == declared.c[c["name"]].nullable
            assert str(c["type"].compile(dialect=connection.dialect)) == str(
                declared.c[c["name"]].type.compile(dialect=connection.dialect)
            )
            assert (c["default"] is not None) == (declared.c[c["name"]].server_default is not None)
        assert reflected.get_pk_constraint(declared.name)["constrained_columns"] == ["id"]
        (fk,) = reflected.get_foreign_keys(declared.name)
        assert (fk["constrained_columns"], fk["referred_table"], fk["referred_columns"]) == (
            ["id"],
            "cw2_eval_runs",
            ["id"],
        )
        (check,) = reflected.get_check_constraints(declared.name)
        assert check["name"] == "ck_dev_campaign_status"
        assert reflected.get_indexes(declared.name) == []
        tree = ast.parse((ROOT / "migrations/versions/0012_dev_campaign_envelope.py").read_text())
        sql = next(
            ast.literal_eval(n.args[0])
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "execute"
        )
        expected = dict(re.findall(r"CREATE FUNCTION (cw6_\w+)\(\).*?AS \$\$(.*?)\$\$;", sql, re.S))
        actual = dict(
            connection.execute(
                text(
                    "SELECT proname, prosrc FROM pg_proc JOIN pg_namespace n ON n.oid=pronamespace "
                    "WHERE n.nspname='public' AND proname LIKE 'cw6_%'"
                )
            ).all()
        )
        assert {k: v.strip() for k, v in actual.items()} == {k: v.strip() for k, v in expected.items()}
        triggers = connection.execute(
            text(
                "SELECT tgname, tgtype, c.relname, tgenabled, pg_get_triggerdef(t.oid) "
                "FROM pg_trigger t JOIN pg_class c ON c.oid=tgrelid "
                "WHERE tgname LIKE 'cw6_%' AND NOT tgisinternal"
            )
        ).all()
        assert {(n, kind, table, enabled) for n, kind, table, enabled, _ in triggers} == {
            ("cw6_dev_immutable", 31, "cw6_dev_campaigns", "O"),
            ("cw6_dev_phase_immutable", 31, "cw4_provider_phases", "O"),
            ("cw6_dev_result_immutable", 31, "cw2_eval_cases", "O"),
            ("cw6_dev_no_truncate", 34, "cw6_dev_campaigns", "O"),
            ("cw6_dev_phase_no_truncate", 34, "cw4_provider_phases", "O"),
            ("cw6_dev_case_no_truncate", 34, "cw2_eval_cases", "O"),
        }
        assert all("EXECUTE FUNCTION cw6_" in definition for *_, definition in triggers)


@pytest.mark.parametrize(
    "change",
    [
        "eval_run_id=NULL, case_id=NULL",
        "eval_run_id=NULL",
        "case_id=NULL",
        "eval_run_id=:other",
        "case_id='D2.V1:cp-a-v1'",
    ],
)
def test_dev_ownership_escape_sql(change, fresh_0011):
    _, _, _, phase = prepared()
    denied(f"UPDATE cw4_provider_phases SET {change} WHERE id=:id", {"id": phase, "other": fresh_0011[1]})


@pytest.mark.parametrize(
    "change",
    [
        "id=gen_random_uuid()",
        "logical_key=logical_key||'-changed'",
        "reserved_at=reserved_at+interval '1 second'",
        "created_at=created_at+interval '1 second'",
        "phase='interpretation'",
        "phase_attempt=2",
        "owner=gen_random_uuid()",
        "fence=fence+1",
        "authorization_id=gen_random_uuid()",
        "authorization_deadline=authorization_deadline+interval '1 second'",
        "request_hash=repeat('a',64)",
        "prompt_revision='changed'",
        "provider='changed'",
        "model='changed'",
        "price_revision='changed'",
        "input_tokens=input_tokens+1",
        "output_tokens=output_tokens+1",
        "reserved_yuan=reserved_yuan+0.001",
        "query_run_id=gen_random_uuid()",
        "conversation_run_id=gen_random_uuid()",
    ],
)
def test_reservation_identity_sql(change):
    _, _, _, phase = prepared()
    before = snapshot("cw4_provider_phases", "id=:id", id=phase)
    denied(
        f"UPDATE cw4_provider_phases SET {change} WHERE id=:id",
        {"id": phase},
        match="dev_|conversation_provider_identity_immutable",
    )
    assert snapshot("cw4_provider_phases", "id=:id", id=phase) == before


@pytest.mark.parametrize("state", ["COMPLETED", "UNKNOWN", "REJECTED"])
@pytest.mark.parametrize(
    "change",
    [
        "usage='{}'::jsonb",
        "result_hash=repeat('a',64)",
        "outcome='changed'",
        "estimated_yuan=9",
        "logical_key=logical_key||'-changed'",
        "request_id='changed'",
        "result='[]'::jsonb",
        "error_code='changed'",
        "updated_at=updated_at+interval '1 second'",
        "dispatched_at=clock_timestamp()",
        "model='changed'",
        "state='PREPARED'",
    ],
)
def test_terminal_whole_receipt_sql(state, change):
    _, _, _, phase = terminal(state)
    before = snapshot("cw4_provider_phases", "id=:id", id=phase)
    denied(f"UPDATE cw4_provider_phases SET {change} WHERE id=:id", {"id": phase})
    assert snapshot("cw4_provider_phases", "id=:id", id=phase) == before


def test_dispatch_timestamp_and_invalid_state_transitions():
    w, p, token, phase = prepared()
    for change in (
        "state='COMPLETED',outcome='known',result_hash=repeat('1',64)",
        "state='DISPATCHED',outcome='unknown'",
        "dispatched_at=clock_timestamp()",
        "usage='{}'::jsonb",
    ):
        denied(f"UPDATE cw4_provider_phases SET {change} WHERE id=:id", {"id": phase})
    campaign.dispatch(w, p.campaign_id, KEY, token["owner"], phase, BODY, Accounting(), p.identities)
    for change in (
        "state='PREPARED'",
        "dispatched_at=dispatched_at+interval '1 second'",
        "state='COMPLETED',outcome='known'",
        "state='UNKNOWN',outcome='known'",
    ):
        denied(f"UPDATE cw4_provider_phases SET {change} WHERE id=:id", {"id": phase})
    campaign.observe(
        w,
        p.campaign_id,
        KEY,
        token["owner"],
        phase,
        dict(result_hash="2" * 64, usage=dict(prompt_tokens=100, completion_tokens=40)),
        known=True,
    )
    with transaction() as db:
        row = db.get(ProviderPhaseRow, phase)
        assert row.state == "COMPLETED" and row.dispatched_at and row.result_hash == "2" * 64


@pytest.mark.parametrize("state", ["PREPARED", "COMPLETED", "UNKNOWN", "REJECTED"])
def test_committed_phase_cannot_delete_or_restore_allowance(state):
    _, p, _, phase = prepared() if state == "PREPARED" else terminal(state)
    before = snapshot("cw4_provider_phases", "id=:id", id=phase)
    denied("DELETE FROM cw4_provider_phases WHERE id=:id", {"id": phase})
    assert snapshot("cw4_provider_phases", "id=:id", id=phase) == before
    with transaction() as db:
        phases = campaign._phases(db, p.campaign_id)
        assert len(phases) == 1 and phases[0].reserved_yuan == Decimal("0.001")
        with pytest.raises(CoreConflict, match="budget_exceeded"):
            campaign._budget(
                phases, campaign.Limits(calls=0, input_tokens=0, output_tokens=0, total_tokens=0, yuan=0)
            )


def test_campaign_delete_recreate_and_truncate_blocked():
    _, p, _, _ = prepared()
    before = snapshot("cw6_dev_campaigns", "id=:id", id=p.campaign_id)
    denied("DELETE FROM cw6_dev_campaigns WHERE id=:id", {"id": p.campaign_id})
    for table in ("cw6_dev_campaigns", "cw4_provider_phases", "cw2_eval_cases"):
        denied(f"TRUNCATE {table} CASCADE", {})
    assert snapshot("cw6_dev_campaigns", "id=:id", id=p.campaign_id) == before


@pytest.mark.parametrize("status", ["COMPLETED", "FAILED", "OUTCOME_UNKNOWN"])
def test_terminal_case_update_delete_and_recovery(status):
    w, p, token, _ = terminal("UNKNOWN" if status == "OUTCOME_UNKNOWN" else "COMPLETED")
    if status != "OUTCOME_UNKNOWN":
        campaign.settle(
            w, p.campaign_id, KEY, token["owner"], {"synthetic": "receipt"}, failed=status == "FAILED"
        )
    before = snapshot("cw2_eval_cases", "eval_run_id=:id AND case_id=:key", id=p.campaign_id, key=KEY)
    for change in (
        "result='{}'::jsonb",
        "execution_attempt=0",
        "max_attempts=3",
        "status='PENDING'",
        "case_id='changed'",
        "eval_run_id=gen_random_uuid()",
        "updated_at=clock_timestamp()",
    ):
        denied(
            f"UPDATE cw2_eval_cases SET {change} WHERE eval_run_id=:id AND case_id=:key",
            {"id": p.campaign_id, "key": KEY},
        )
    denied(
        "DELETE FROM cw2_eval_cases WHERE eval_run_id=:id AND case_id=:key", {"id": p.campaign_id, "key": KEY}
    )
    assert snapshot("cw2_eval_cases", "eval_run_id=:id AND case_id=:key", id=p.campaign_id, key=KEY) == before
    assert campaign.begin(w, p.campaign_id, KEY)["status"] == status


def test_pending_running_case_attempts_and_identity():
    w, p, _ = start()
    for key in (KEY, "D2.V1:cp-a-v1"):
        for change in (
            "execution_attempt=0" if key == KEY else "execution_attempt=1",
            "max_attempts=2",
            "status='PENDING'" if key == KEY else "status='RUNNING'",
            "fence=fence+1",
            "owner=gen_random_uuid()",
            "case_id='changed'",
        ):
            denied(
                f"UPDATE cw2_eval_cases SET {change} WHERE eval_run_id=:id AND case_id=:key",
                {"id": p.campaign_id, "key": key},
            )
        denied(
            "DELETE FROM cw2_eval_cases WHERE eval_run_id=:id AND case_id=:key",
            {"id": p.campaign_id, "key": key},
        )
    campaign.cancel(w, p.campaign_id)
    with pytest.raises(CoreConflict):
        campaign.begin(w, p.campaign_id, "D2.V1:cp-a-v1")


def test_never_committed_reservation_rolls_back_and_stop_commits(monkeypatch):
    w, p, token = start()
    original = campaign._check
    calls = 0

    def after_flush(db, row, policy, now, case=None):
        nonlocal calls
        calls += 1
        if calls >= 2:
            now = token["deadline"] + timedelta(seconds=1)
        return original(db, row, policy, now, case)

    monkeypatch.setattr(campaign, "_check", after_flush)
    with pytest.raises(CoreConflict, match="target_not_active"):
        campaign.prepare(w, p.campaign_id, KEY, token["owner"], "generation", BODY, Accounting())
    with transaction() as db:
        assert campaign._phases(db, p.campaign_id) == []
        assert db.get(DevCampaignRow, p.campaign_id).status == "STOPPED"


@pytest.mark.parametrize(
    "patch",
    [
        {"case_id": None},
        {"phase_attempt": 2},
        {"phase": "judge"},
        {"model": None},
        {"input_tokens": 0},
        {"output_tokens": None},
        {"reserved_yuan": 0},
        {"authorization_id": None},
        {"authorization_deadline": None},
        {"request_hash": None},
        {"logical_key": "changed"},
        {"state": "COMPLETED"},
        {"usage": {}},
        {"outcome": "known"},
        {"query_run_id": str(uuid4())},
    ],
)
def test_dev_insert_validates_new_ownership(patch):
    import json

    _, _, _, phase = prepared()
    patch = {"id": str(uuid4()), **patch}
    denied(
        "INSERT INTO cw4_provider_phases SELECT "
        "(jsonb_populate_record(NULL::cw4_provider_phases,to_jsonb(r)||CAST(:patch AS jsonb))).* "
        "FROM cw4_provider_phases r WHERE id=:id",
        {"id": phase, "patch": json.dumps(patch)},
    )


def test_valid_insert_and_transaction_rollback_without_delete():
    w, p, token, phase = prepared()
    with pytest.raises(CoreConflict, match="rollback_sentinel"), transaction() as db:
        row = db.get(ProviderPhaseRow, phase)
        values = {c.name: getattr(row, c.name) for c in ProviderPhaseRow.__table__.columns}
        values.update(
            id=uuid4(), phase="interpretation", logical_key=f"dev:{p.campaign_id}:{KEY}:interpretation"
        )
        db.add(ProviderPhaseRow(**values))
        db.flush()  # Valid DEV INSERT; transaction rollback invokes no DELETE trigger.
        raise CoreConflict("rollback_sentinel")
    with transaction() as db:
        assert len(campaign._phases(db, p.campaign_id)) == 1
    phase2 = campaign.prepare(w, p.campaign_id, KEY, token["owner"], "interpretation", BODY, Accounting())
    assert phase2 != phase


def test_cannot_rebind_between_two_dev_campaigns():
    _, p, _, phase = prepared()
    _, other, _, _ = prepared()
    denied(
        "UPDATE cw4_provider_phases SET eval_run_id=:other WHERE id=:id",
        {"other": other.campaign_id, "id": phase},
    )
    denied(
        "UPDATE cw2_eval_cases SET eval_run_id=:other,case_id='new' WHERE eval_run_id=:id AND case_id=:key",
        {"other": other.campaign_id, "id": p.campaign_id, "key": KEY},
    )


def test_nondev_workflows_and_entry_boundary(fresh_0011):
    _, legacy, phase = fresh_0011
    _, p, _, _ = prepared()
    denied(
        "UPDATE cw4_provider_phases SET eval_run_id=:dev, case_id=:key WHERE id=:id",
        {"dev": p.campaign_id, "key": KEY, "id": phase},
    )
    denied(
        "UPDATE cw2_eval_cases SET eval_run_id=:dev, case_id='new' WHERE eval_run_id=:id",
        {"dev": p.campaign_id, "id": legacy},
    )
    with transaction() as db:
        db.execute(
            text(
                "UPDATE cw4_provider_phases SET logical_key=logical_key||'-legacy', "
                "eval_run_id=NULL,case_id=NULL,usage='{}'::jsonb WHERE id=:id"
            ),
            {"id": phase},
        )
        db.execute(
            text(
                "UPDATE cw2_eval_cases SET execution_attempt=2,max_attempts=4, status='FAILED' "
                "WHERE eval_run_id=:id"
            ),
            {"id": legacy},
        )
    with transaction() as db:
        db.execute(text("DELETE FROM cw4_provider_phases WHERE id=:id"), {"id": phase})
        db.execute(text("DELETE FROM cw2_eval_cases WHERE eval_run_id=:id"), {"id": legacy})


@pytest.mark.parametrize("mode", ["DISABLED", "SYNTHETIC"])
def test_campaign_finite_status_and_frozen_envelope(mode):
    from test_v02_dev_remediation import policy

    workspace, scope = metadata()
    p = policy(mode)
    campaign.create(workspace, scope.kb_id, p)
    for change in (
        "status='ACTIVE'",
        "policy=policy||jsonb_build_object('altered',true)",
        "policy_sha256=repeat('a',64)",
        "expires_at=expires_at+interval '1 minute'",
        "deadline=deadline+interval '1 minute'",
    ):
        denied(f"UPDATE cw6_dev_campaigns SET {change} WHERE id=:id", {"id": p.campaign_id})
    if mode == "SYNTHETIC":
        campaign.cancel(workspace, p.campaign_id)
        denied("UPDATE cw6_dev_campaigns SET status='SYNTHETIC' WHERE id=:id", {"id": p.campaign_id})
