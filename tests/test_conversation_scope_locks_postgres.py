"""Shared scope readers still fence concurrent non-key source mutations."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text, update
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import pytestmark as pytestmark
from test_conversation_postgres import sample as sample

from citeweave import conversations as core
from citeweave.conversation_contract import CoreConflict
from citeweave.db import transaction
from citeweave.domain import DocumentRow, KnowledgeBaseRow, VersionRow


def hold_scope(sample, acquired, release):
    with transaction() as db:
        core._scope(db, sample[0], sample[2].scope, current=True)
        acquired.set()
        assert release.wait(10)


def wait_for_lock(identity):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with transaction() as db:
            waiting = db.scalar(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"), {"pid": identity}
            )
            if waiting == "Lock":
                return
        time.sleep(0.02)
    pytest.fail("expected actual PostgreSQL row-lock wait was not observed")


def mutation(sample, target):
    _, _, body = sample
    if target == "workspace":
        return (
            update(KnowledgeBaseRow)
            .where(KnowledgeBaseRow.id == body.scope.kb_id)
            .values(workspace_id=uuid4())
        )
    if target == "document":
        return update(DocumentRow).where(DocumentRow.kb_id == body.scope.kb_id).values(active_version_id=None)
    return update(VersionRow).where(VersionRow.id == body.scope.version_ids[0]).values(status="PENDING")


def rejected(sample, target):
    with transaction() as db:
        expected = HTTPException if target == "workspace" else CoreConflict
        with pytest.raises(expected):
            core._scope(db, sample[0], sample[2].scope, current=True)


def test_independent_scope_readers_overlap_without_serializing_shared_source(sample):
    first, second, release = Event(), Event(), Event()
    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(hold_scope, sample, first, release)
        assert first.wait(5)
        b = pool.submit(hold_scope, sample, second, release)
        try:
            assert second.wait(2), "an independent scope reader serialized on the shared source"
        finally:
            release.set()
        a.result(5)
        b.result(5)


@pytest.mark.parametrize("target", ["workspace", "document", "version"])
def test_scope_reader_blocks_non_key_source_change_until_commit(sample, target):
    acquired, release, ready, done = Event(), Event(), Event(), Event()
    writer_pid = []

    def writer():
        with transaction() as db:
            writer_pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            ready.set()
            db.execute(mutation(sample, target))
        done.set()

    with ThreadPoolExecutor(2) as pool:
        read = pool.submit(hold_scope, sample, acquired, release)
        assert acquired.wait(5)
        write = pool.submit(writer)
        try:
            assert ready.wait(5)
            wait_for_lock(writer_pid[0])
            assert not done.is_set()
        finally:
            release.set()
        read.result(5)
        write.result(5)
    rejected(sample, target)


@pytest.mark.parametrize("target", ["workspace", "document", "version"])
def test_committing_source_change_is_rechecked_by_waiting_reader(sample, target):
    changed, release, ready = Event(), Event(), Event()
    reader_pid = []

    def writer():
        with transaction() as db:
            db.execute(mutation(sample, target))
            changed.set()
            assert release.wait(10)

    def reader():
        with transaction() as db:
            reader_pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            ready.set()
            expected = HTTPException if target == "workspace" else CoreConflict
            with pytest.raises(expected):
                core._scope(db, sample[0], sample[2].scope, current=True)

    with ThreadPoolExecutor(2) as pool:
        write = pool.submit(writer)
        assert changed.wait(5)
        read = pool.submit(reader)
        try:
            assert ready.wait(5)
            wait_for_lock(reader_pid[0])
        finally:
            release.set()
        write.result(5)
        read.result(5)
