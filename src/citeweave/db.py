from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from citeweave.settings import settings


@lru_cache
def engine():
    return create_engine(
        settings().db_url(),
        pool_size=4,
        max_overflow=2,
        pool_timeout=5,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
    )


@contextmanager
def transaction():
    with Session(engine(), expire_on_commit=False) as session, session.begin():
        yield session


def migrate():
    from alembic import command
    from alembic.config import Config

    from citeweave.settings import ROOT

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")
