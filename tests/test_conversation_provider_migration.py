"""Upgrade populated 0009 in a disposable database, preserving legacy shapes."""

from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from pydantic import SecretStr
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from test_conversation_postgres import execution, metadata
from test_conversation_postgres import pytestmark as pytestmark

from citeweave import conversations as core
from citeweave.conversation_contract import Admission
from citeweave.db import engine, migrate, transaction
from citeweave.domain import Base, EvalCaseRow, EvalRunRow, ProviderPhaseRow, QueryRunRow
from citeweave.settings import ROOT, settings


def test_populated_0009_upgrade_repeat_constraints_and_legacy_readers():
    config = settings()
    original = config.database_url
    url = make_url(config.db_url())
    assert url.host in {"127.0.0.1", "localhost", "::1"}
    database = "cw_conversation_test_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3})
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text('CREATE DATABASE "' + database + '"'))
        created = True
        engine.cache_clear()
        config.database_url = SecretStr(url.set(database=database).render_as_string(hide_password=False))
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "migrations"))
        command.upgrade(cfg, "0009")
        workspace, scope = metadata()
        # Seed the historical shape with reflected tables, never today's ORM.
        from decimal import Decimal

        from sqlalchemy import MetaData, Table

        from citeweave.catalog import fingerprint
        from citeweave.conversation_contract import RunView
        from citeweave.conversation_provider import RunAuthorization, authorize_run

        conv_id, turn_id, run_id = uuid4(), uuid4(), uuid4()
        request = Admission(question="Original fixture", scope=scope, expected_head=None)
        owner = execution()
        with transaction() as db:
            tables = MetaData()
            conv_table = Table("cw5_conversations", tables, autoload_with=db.connection())
            turn_table = Table("cw5_turns", tables, autoload_with=db.connection())
            run_table = Table("cw5_runs", tables, autoload_with=db.connection())
            db.execute(
                conv_table.insert().values(
                    id=conv_id, workspace_id=workspace, key="before-migration", fence=1
                )
            )
            db.execute(
                turn_table.insert().values(
                    id=turn_id, conversation_id=conv_id, request=request.model_dump(mode="json")
                )
            )
            db.execute(
                run_table.insert().values(
                    id=run_id,
                    conversation_id=conv_id,
                    turn_id=turn_id,
                    key="before",
                    fingerprint=fingerprint(request.model_dump(mode="json")),
                    owner=owner.owner,
                    fence=1,
                    deadline=owner.deadline,
                    status="ADMITTED",
                )
            )
            before_run = db.scalar(text("SELECT to_jsonb(r) FROM cw5_runs r WHERE id=:id"), {"id": run_id})
        query_id, eval_id = uuid4(), uuid4()
        with transaction() as db:
            db.add(
                QueryRunRow(
                    id=query_id,
                    workspace_id=workspace,
                    kb_id=scope.kb_id,
                    key="legacy",
                    fingerprint="0" * 64,
                    question="Legacy",
                    status="FAILED",
                )
            )
            db.add(
                EvalRunRow(
                    id=eval_id,
                    workspace_id=workspace,
                    kb_id=scope.kb_id,
                    key="legacy",
                    dataset_id="original",
                    dataset_hash="0" * 64,
                    split="dev",
                    versions={},
                    runtime_config={},
                )
            )
            db.flush()
            db.add(EvalCaseRow(eval_run_id=eval_id, case_id="original"))
            db.flush()
            for q, e, case in (
                (query_id, None, None),
                (None, eval_id, "original"),
                (query_id, eval_id, "original"),
            ):
                identity = uuid4()
                db.execute(
                    text("""INSERT INTO cw4_provider_phases
                    (id,query_run_id,eval_run_id,case_id,logical_key,phase,phase_attempt,state,
                     owner,fence,reserved_at,reserved_yuan,outcome)
                    VALUES (:id,:q,:e,:case,:key,'answer',1,'PREPARED',:owner,1,clock_timestamp(),0.10,'not_dispatched')"""),
                    dict(id=identity, q=q, e=e, case=case, key=str(identity), owner=uuid4()),
                )
            before = list(
                db.execute(text("SELECT to_jsonb(p) FROM cw4_provider_phases p ORDER BY id")).scalars()
            )
        command.upgrade(cfg, "0010")
        with transaction() as db:
            assert (
                db.scalar(text("SELECT to_jsonb(r) FROM cw5_runs r WHERE id=:id"), {"id": run_id})
                == before_run
            )
        migrate()
        migrate()
        run = core.read_run_id(workspace, conv_id, run_id).run
        assert isinstance(run, RunView) and run.owner == owner.owner
        with transaction() as db:
            after_run = db.scalar(text("SELECT to_jsonb(r) FROM cw5_runs r WHERE id=:id"), {"id": run_id})
            assert all(after_run[k] == v for k, v in before_run.items())
            assert all(after_run[k] is None for k in after_run.keys() - before_run.keys())
        authorize_run(
            workspace,
            run,
            RunAuthorization(
                id=uuid4(),
                run_id=run.id,
                expires_at=run.deadline,
                max_calls=3,
                max_input_tokens=300,
                max_output_tokens=300,
                max_yuan=Decimal("0.003"),
            ),
        )
        with transaction() as db:
            after = list(db.scalars(select(ProviderPhaseRow).order_by(ProviderPhaseRow.id)))
            assert len(after) == len(before) == 3
            for old, row in zip(before, after, strict=True):
                current = db.scalar(
                    text("SELECT to_jsonb(p) FROM cw4_provider_phases p WHERE id=:id"), {"id": row.id}
                )
                assert all(current[key] == value for key, value in old.items())
                assert row.conversation_run_id is None and row.authorization_id is None
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0011"
        # Audit DB constraint itself, rather than only the service's input checks.
        from test_conversation_provider_postgres import authorization

        from citeweave.conversation_provider import prepare

        phase = prepare(workspace, run, authorization(run))
        with transaction() as db:
            values = (
                db.execute(text("SELECT * FROM cw4_provider_phases WHERE id=:id"), {"id": phase.id})
                .mappings()
                .one()
            )
        # Driver adaptation for JSON values uses the typed Table insert.
        for changed, constraint in (
            ({"query_run_id": query_id}, "ck_provider_conversation_owner"),
            ({"eval_run_id": eval_id, "case_id": "original"}, "ck_provider_conversation_owner"),
            ({"conversation_run_id": uuid4()}, "fk_provider_conversation_run"),
            ({"authorization_id": None}, "ck_provider_conversation_authorization"),
            ({"phase": "judge"}, "ck_provider_conversation_authorization"),
            ({"phase_attempt": 2}, "ck_provider_conversation_authorization"),
            ({"phase": "generation"}, "uq_provider_conversation_purpose"),
            ({"authorization_id": phase.authorization_id}, "uq_provider_conversation_authorization"),
            ({"logical_key": phase.logical_key}, "cw4_provider_phases_logical_key_phase_attempt_key"),
        ):
            duplicate = dict(
                values, id=uuid4(), phase="interpretation", logical_key=str(uuid4()), authorization_id=uuid4()
            )
            duplicate.update(changed)
            with pytest.raises(IntegrityError) as exc:
                with transaction() as db:
                    db.execute(ProviderPhaseRow.__table__.insert().values(**duplicate))
            assert exc.value.orig.diag.constraint_name == constraint
        with engine().connect() as connection:
            ctx = MigrationContext.configure(
                connection,
                opts={
                    "include_object": lambda obj, name, kind, reflected, compare_to: (
                        name in {"cw4_provider_phases", "cw5_runs"} if kind == "table" else True
                    )
                },
            )
            assert compare_metadata(ctx, Base.metadata) == []
    finally:
        if created:
            engine().dispose()
            engine.cache_clear()
            config.database_url = original
            with admin.connect() as connection:
                connection.execute(text('DROP DATABASE "' + database + '"'))
        admin.dispose()
