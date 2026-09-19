import importlib.util
from pathlib import Path

import pytest


def helper():
    spec = importlib.util.spec_from_file_location(
        "candidate", Path(__file__).parents[1] / "scripts/public_candidate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_excludes_unreviewed_docs_and_private_exports(tmp_path, monkeypatch):
    candidate = helper()
    names = ["README.md", "docs/unreviewed.md", "docs/reports/private.json", "evals/results/private.json"]
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("original fixture", encoding="utf-8")
    monkeypatch.setattr(candidate, "ROOT", tmp_path)
    monkeypatch.setattr(candidate.subprocess, "check_output", lambda *a, **kw: "\0".join(names).encode())
    assert candidate.candidate_files() == ["README.md"]


def test_candidate_rejects_pdf_and_machine_specific_paths(tmp_path, monkeypatch):
    candidate = helper()
    monkeypatch.setattr(candidate, "ROOT", tmp_path)
    monkeypatch.setattr(candidate.subprocess, "check_output", lambda *a, **kw: b"tests/unlicensed.pdf\0")
    with pytest.raises(ValueError, match="unapproved_binary"):
        candidate.candidate_files()
    path = "/".join(["Z:", "Users", "fixture", "private.txt"])
    with pytest.raises(ValueError, match="private_machine_path"):
        candidate.check_content("example.md", path.encode())
