"""A populated 0013 event upgrades unchanged; historical facts remain absent."""

from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from test_conversation_postgres import pytestmark as pytestmark

from citeweave.db import engine
from citeweave.settings import ROOT, settings


def test_populated_0013_event_upgrade_preserves_all_facts():
    config = settings()
    original = config.database_url
    url = make_url(config.db_url())
    assert url.host in {"127.0.0.1", "localhost", "::1"}
    name = "cw_operational_migration_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    target = None
    created = False
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
        assert ScriptDirectory.from_config(cfg).get_heads() == ["0014"]
        command.upgrade(cfg, "0013")
        c, t, r, e = (uuid4() for _ in range(4))
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
                    "INSERT INTO cw5_runs (id,conversation_id,turn_id,key,fingerprint,owner,fence,deadline,status) VALUES (:r,:c,:t,'old',:hash,:owner,1,now()+interval '5 minutes','ADMITTED')"
                ),
                {"r": r, "c": c, "t": t, "hash": "a" * 64, "owner": uuid4()},
            )
            db.execute(
                text(
                    "INSERT INTO cw5_run_events (id,run_id,created_at,kind,fence) VALUES (:e,:r,clock_timestamp(),'admitted',1)"
                ),
                {"e": e, "r": r},
            )
            before = db.scalar(text("SELECT to_jsonb(e) FROM cw5_run_events e"))
        command.upgrade(cfg, "head")
        command.upgrade(cfg, "head")
        with target.connect() as db:
            after = db.scalar(text("SELECT to_jsonb(e) FROM cw5_run_events e"))
            assert all(after[k] == v for k, v in before.items())
            assert after["phase"] is None and after["current_fence"] is None
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0014"
            assert (
                db.scalar(
                    text(
                        "SELECT count(*) FROM pg_trigger WHERE tgrelid='cw5_run_events'::regclass AND NOT tgisinternal"
                    )
                )
                == 2
            )
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
