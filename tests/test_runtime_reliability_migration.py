"""Populated 0012 -> 0013 migration preserves original authority and grants."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import pytestmark as pytestmark

from citeweave.db import engine
from citeweave.settings import ROOT, settings


def test_populated_0012_upgrade_preserves_rows_and_grant_capacity():
    from sqlalchemy.engine import make_url

    config = settings()
    original = config.database_url
    url = make_url(config.db_url())
    name = "cw_reliability_migration_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    created = False
    target = None
    try:
        with admin.connect() as db:
            db.execute(text('CREATE DATABASE "' + name + '"'))
        created = True
        engine().dispose()
        engine.cache_clear()
        config.database_url = SecretStr(url.set(database=name).render_as_string(hide_password=False))
        target = create_engine(config.db_url())
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "migrations"))
        command.upgrade(cfg, "0012")
        c, t, r, phase, owner = (uuid4() for _ in range(5))
        with target.begin() as db:
            db.execute(
                text("INSERT INTO cw5_conversations (id,workspace_id,key,fence) VALUES (:c,:w,'old',1)"),
                {"c": c, "w": uuid4()},
            )
            db.execute(
                text("INSERT INTO cw5_turns (id,conversation_id,request) VALUES (:t,:c,'{}')"),
                {"t": t, "c": c},
            )
            db.execute(
                text(
                    "INSERT INTO cw5_runs (id,conversation_id,turn_id,key,fingerprint,owner,fence,deadline,status) VALUES (:r,:c,:t,'old',:hash,:owner,1,:deadline,'ADMITTED')"
                ),
                {
                    "r": r,
                    "c": c,
                    "t": t,
                    "hash": "f" * 64,
                    "owner": owner,
                    "deadline": datetime.now(timezone.utc) + timedelta(minutes=5),
                },
            )
            db.execute(
                text(
                    "INSERT INTO cw4_provider_phases (id,conversation_run_id,logical_key,phase,phase_attempt,state,owner,fence,reserved_at,reserved_yuan,outcome,provider,model,price_revision,authorization_id,authorization_deadline,input_tokens,output_tokens,prompt_revision,request_hash) VALUES (:p,:r,'migration-synthetic','generation',1,'PREPARED',:owner,1,now(),0.001,'not_dispatched','deepseek','deepseek-flash','deepseek-flash-CNY-2026-09-13',:auth,now()+interval '5 minutes',100,100,'synthetic',:hash)"
                ),
                {"p": phase, "r": r, "owner": owner, "auth": uuid4(), "hash": "a" * 64},
            )
            before = {
                table: db.scalar(text(f"SELECT to_jsonb(x) FROM {table} x LIMIT 1"))
                for table in ("cw5_runs", "cw4_provider_phases")
            }
        command.upgrade(cfg, "head")
        command.upgrade(cfg, "head")
        with target.begin() as db:
            for table, previous in before.items():
                after = db.scalar(text(f"SELECT to_jsonb(x) FROM {table} x LIMIT 1"))
                assert all(after[key] == value for key, value in previous.items())
            assert db.scalar(text("SELECT transport_limit FROM cw4_provider_phases")) == 1
            assert db.scalar(text("SELECT transport_attempt FROM cw4_provider_phases")) == 0
            assert db.scalar(text("SELECT execution_started_at FROM cw5_runs")) is None
            assert db.scalar(text("SELECT count(*) FROM cw5_run_events")) == 0
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0013"
    finally:
        engine().dispose()
        engine.cache_clear()
        config.database_url = original
        if target is not None:
            target.dispose()
        if created:
            with admin.connect() as db:
                db.execute(text('DROP DATABASE "' + name + '"'))
        admin.dispose()
