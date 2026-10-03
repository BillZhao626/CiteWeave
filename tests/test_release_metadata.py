"""Current release checks exclude ignored history but still reject tracked identity drift."""

import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def metadata_fixture(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("release_metadata", ROOT / "scripts/check_release.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    monkeypatch.setattr(check, "ROOT", tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n', encoding="utf-8")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "citeweave-rag"\nversion = "0.2.0"\n', encoding="utf-8"
    )
    for relative in ("apps/web/package.json", "apps/web/openapi.json", "contracts/openapi.json"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": "0.2.0", "info": {"version": "0.2.0"}}), encoding="utf-8")
    (tmp_path / "README.md").write_text("Current release 0.2.0", encoding="utf-8")
    history = tmp_path / "docs/ignored-history.md"
    history.parent.mkdir()
    history.write_text("Historical identity " + "0." + "3.0a1", encoding="utf-8")
    monkeypatch.setattr(check.subprocess, "run", lambda *a, **k: CompletedProcess(a, 0, b"README.md\0", b""))
    return check


def test_ignored_historical_metadata_does_not_block_current_checkout(monkeypatch, tmp_path):
    check = metadata_fixture(monkeypatch, tmp_path)
    check.check_release_metadata()


def test_tracked_obsolete_identity_still_blocks_release(monkeypatch, tmp_path):
    check = metadata_fixture(monkeypatch, tmp_path)
    (tmp_path / "README.md").write_text("Obsolete active identity " + "0." + "3.0a1", encoding="utf-8")
    with pytest.raises(SystemExit, match="Obsolete release identity"):
        check.check_release_metadata()
