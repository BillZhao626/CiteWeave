"""Release smoke must preserve colliding resources and report cleanup failures honestly."""

import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def smoke_fixture(monkeypatch, tmp_path, *, collision=None, startup_failure=False, leftover=False):
    spec = importlib.util.spec_from_file_location("release_smoke", ROOT / "scripts/smoke_release.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr(smoke, "uuid4", lambda: SimpleNamespace(hex="a" * 32))
    web = tmp_path / "apps/web/dist"
    web.mkdir(parents=True)
    (web / "index.html").write_text("synthetic frontend", encoding="utf-8")
    project = "cw-release-" + "a" * 12
    config = {
        "networks": {"default": {"internal": True, "name": project + "_default"}},
        "volumes": {"pgdata": {"name": project + "_pgdata"}},
        "services": {
            name: {"environment": {"DEEPSEEK_API_KEY": ""}, "volumes": [{"type": "volume"}]}
            for name in ("postgres", "broker", "qdrant", "api", "m1-worker")
        },
    }
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        code, output = 0, ""
        if args[:3] == ["docker", "compose", "version"]:
            output = "2.40.3"
        elif "config" in args:
            output = json.dumps(config)
        elif "ps" in args and "json" in args:
            output = '[{"Name":"existing"}]' if collision == "container" else "[]"
        elif args[:3] == ["docker", collision, "ls"]:
            output = "existing-resource"
        elif (
            args[:3] == ["docker", "volume", "ls"]
            and collision == "unlabelled_volume"
            and "--filter" not in args
        ):
            output = project + "_pgdata"
        elif "up" in args and startup_failure:
            code = 1
        elif args[:3] == ["docker", "volume", "ls"] and leftover and any("down" in a for a in calls):
            output = project + "_pgdata"
        return CompletedProcess(args, code, output, "")

    monkeypatch.setattr(smoke.subprocess, "run", run)
    return smoke, calls, tmp_path / ".runtime/release/v0.2/service-smoke.json"


@pytest.mark.parametrize("collision", ["container", "volume", "network", "unlabelled_volume"])
def test_resource_collision_never_tears_down_existing_project(monkeypatch, tmp_path, collision):
    smoke, calls, receipt = smoke_fixture(monkeypatch, tmp_path, collision=collision)
    with pytest.raises(SystemExit):
        smoke.main()
    assert not any("build" in args or "up" in args or "down" in args for args in calls)
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "FAIL"


def test_partial_startup_failure_cleans_only_owned_project(monkeypatch, tmp_path):
    smoke, calls, receipt = smoke_fixture(monkeypatch, tmp_path, startup_failure=True)
    with pytest.raises(SystemExit):
        smoke.main()
    teardown = [args for args in calls if "down" in args]
    assert len(teardown) == 1
    assert teardown[0][teardown[0].index("-p") + 1] == "cw-release-" + "a" * 12
    assert "--volumes" in teardown[0] and "--timeout" in teardown[0]
    report = json.loads(receipt.read_text(encoding="utf-8"))
    assert report["status"] == "FAIL" and report["failed_stage"] == "service startup"
    assert report["provider_model_judge_calls"] == report["spend_cny"] == 0


def test_remaining_volume_never_records_cleanup_as_pass(monkeypatch, tmp_path):
    smoke, calls, receipt = smoke_fixture(monkeypatch, tmp_path, startup_failure=True, leftover=True)
    with pytest.raises(SystemExit):
        smoke.main()
    report = json.loads(receipt.read_text(encoding="utf-8"))
    assert any("down" in args for args in calls)
    assert report["status"] == "FAIL" and "cleanup_failure_class" in report
    assert not any(c["name"] == "bounded clean shutdown" and c["status"] == "PASS" for c in report["checks"])
