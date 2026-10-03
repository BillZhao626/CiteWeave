"""Bounded provider-free smoke of existing release wiring with disposable resources."""

import json
import os
import re
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    if not (ROOT / "apps/web/dist/index.html").is_file():
        raise SystemExit("Build the frontend first; see docs/QUICKSTART.md")
    # Never inherit operator configuration or a live authorization.
    env = {k: v for k, v in os.environ.items() if not k.startswith("CW_")}
    env["DEEPSEEK_API_KEY"] = ""
    project = "cw-release-" + uuid4().hex[:12]
    password, token = secrets.token_hex(24), secrets.token_hex(32)
    checks = []
    stage = [None]

    def run(label, args, timeout=90):
        stage[0] = label
        result = subprocess.run(
            args,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.returncode:
            # Do not emit Compose config, credentials, database URLs or service error bodies.
            raise RuntimeError(f"{label}: exit {result.returncode}")
        return result.stdout.strip()

    receipts = ROOT / ".runtime/release/v0.2"
    receipts.mkdir(parents=True, exist_ok=True)
    report = {"project": project, "checks": checks, "provider_model_judge_calls": 0, "spend_cny": 0}
    with tempfile.TemporaryDirectory(prefix="smoke-", dir=receipts) as folder:
        local = Path(folder)
        credentials = local / "credentials.env"
        credentials.write_text(f"CW_DB_PASSWORD={password}\nCW_ADMIN_TOKEN={token}\n", encoding="utf-8")
        override = local / "isolation.yml"
        # Existing service commands, images, healthchecks and depends_on remain authoritative.
        override.write_text(
            f"""services:
  postgres:
    ports: !reset []
  broker:
    ports: !reset []
  qdrant:
    ports: !reset []
  api:
    image: {project}:local
    ports: !reset []
    volumes: !override [release_blobs:/app/blobs]
    environment:
      CW_MODEL_URL: http://127.0.0.1:9
      DEEPSEEK_API_KEY: ''
  m1-worker:
    image: {project}:local
    restart: 'no'
    volumes: !override [release_blobs:/app/blobs, release_faults:/app/faults]
    environment:
      CW_MODEL_URL: http://127.0.0.1:9
      DEEPSEEK_API_KEY: ''
      CW_ENABLE_FAULTS: 'false'
volumes:
  release_blobs:
  release_faults:
networks:
  default:
    internal: true
""",
            encoding="utf-8",
        )
        compose = [
            "docker",
            "compose",
            "-p",
            project,
            "--env-file",
            str(credentials),
            "-f",
            str(ROOT / "deploy/compose.m0.yml"),
            "-f",
            str(ROOT / "deploy/compose.m1.yml"),
            "-f",
            str(override),
        ]

        def check(label, args, timeout=90):
            run(label, args, timeout)
            checks.append({"name": label, "status": "PASS"})
            print(f"PASS {label}", flush=True)

        def api_check(label, code):
            check(label, compose + ["exec", "-T", "api", "python", "-c", code])

        failure = None
        cleanup_owned = False
        try:
            version = run("compose version", ["docker", "compose", "version", "--short"])
            parts = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version)
            if not parts or tuple(map(int, parts.groups())) < (2, 24, 4):
                raise RuntimeError("Docker Compose 2.24.4+ required for isolation tags")
            report["compose_version"] = version
            config = json.loads(run("compose config", compose + ["config", "--format", "json"]))
            if config["networks"]["default"].get("internal") is not True:
                raise RuntimeError("smoke network must be internal")
            for volume in config.get("volumes", {}).values():
                if volume.get("external") or not volume.get("name", "").startswith(project + "_"):
                    raise RuntimeError("volume is outside the disposable project")
            network = config["networks"]["default"]
            if network.get("external") or network.get("name") != project + "_default":
                raise RuntimeError("network is outside the disposable project")
            for service in ("postgres", "broker", "qdrant", "api", "m1-worker"):
                spec = config["services"][service]
                if spec.get("ports") or any(v["type"] != "volume" for v in spec.get("volumes", [])):
                    raise RuntimeError("smoke requires no host ports or bind mounts")
            for service in ("api", "m1-worker"):
                if config["services"][service]["environment"]["DEEPSEEK_API_KEY"] != "":
                    raise RuntimeError("smoke provider key must be empty")
            if json.loads(run("resource collision", compose + ["ps", "-a", "--format", "json"]) or "[]"):
                raise RuntimeError("existing container collision")
            volume_names = {v["name"] for v in config.get("volumes", {}).values()}
            if volume_names.intersection(
                run("volume name collision", ["docker", "volume", "ls", "-q"]).splitlines()
            ):
                raise RuntimeError("existing named volume collision")
            if (
                network["name"]
                in run(
                    "network name collision", ["docker", "network", "ls", "--format", "{{.Name}}"]
                ).splitlines()
            ):
                raise RuntimeError("existing named network collision")
            for resource in ("volume", "network"):
                if run(
                    f"{resource} collision",
                    [
                        "docker",
                        resource,
                        "ls",
                        "-q",
                        "--filter",
                        f"label=com.docker.compose.project={project}",
                    ],
                ):
                    raise RuntimeError(f"existing {resource} collision")
            # Arm cleanup only after proving this namespace has no existing resources.
            cleanup_owned = True
            checks.append({"name": "isolated real Compose config", "status": "PASS"})
            check("release image build", compose + ["build", "api"], timeout=900)
            check(
                "service startup",
                compose
                + [
                    "up",
                    "-d",
                    "--wait",
                    "--wait-timeout",
                    "120",
                    "postgres",
                    "broker",
                    "qdrant",
                    "api",
                    "m1-worker",
                ],
                180,
            )
            check(
                "PostgreSQL readiness", compose + ["exec", "-T", "postgres", "pg_isready", "-U", "citeweave"]
            )
            assert run("Redis readiness", compose + ["exec", "-T", "broker", "redis-cli", "ping"]) == "PONG"
            checks.append({"name": "Redis readiness", "status": "PASS"})
            api_check(
                "Qdrant readiness",
                "import urllib.request; urllib.request.urlopen('http://qdrant:6333/readyz', timeout=5)",
            )
            api_check(
                "API durable readiness",
                "import json,urllib.request; "
                "r=json.load(urllib.request.urlopen('http://localhost:8000/health/ready',timeout=5)); "
                "assert r['status']=='ready' and r['capability']=='durable_api'",
            )
            api_check(
                "API version",
                "import json,urllib.request; "
                "r=json.load(urllib.request.urlopen('http://localhost:8000/openapi.json',timeout=5)); "
                "assert r['info']['version']=='0.2.0'",
            )
            api_check(
                "repeat migration and empty durable tables",
                "from citeweave.db import migrate,transaction; "
                "from sqlalchemy import text; migrate(); "
                'exec("with transaction() as db:\\n'
                " assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0014'\\n"
                " for name in ('cw5_runs','cw4_provider_phases','cw1_ingestion_jobs','cw1_query_runs','cw1_documents'):\\n"
                "  assert db.execute(text('SELECT count(*) FROM '+name)).scalar_one()==0\")",
            )
            api_check(
                "static frontend and module asset",
                "import re,urllib.request; "
                "s=urllib.request.urlopen('http://localhost:8000/',timeout=5).read().decode(); "
                'a=re.search(r\'src="(/assets/[^"]+\\.js)"\',s); assert a; '
                "r=urllib.request.urlopen('http://localhost:8000'+a[1],timeout=5); "
                "assert 'javascript' in r.headers['content-type'] and len(r.read())>0",
            )
            api_check(
                "PDF.js assets and original fixture",
                "import urllib.request; from pathlib import Path; "
                "assert urllib.request.urlopen('http://localhost:8000/original-handbook.pdf',timeout=5).read().startswith(b'%PDF'); "
                "assert urllib.request.urlopen('http://localhost:8000/pdfjs/LICENSE',timeout=5).read(); "
                "assert Path('/app/apps/web/dist/THIRD_PARTY_NOTICES.txt').read_bytes().startswith(b'CiteWeave frontend third-party notices')",
            )
            # Celery imports are lazy; no task is sent to the empty queue.
            deadline = time.monotonic() + 30
            while True:
                try:
                    api_check(
                        "empty-queue Celery worker ping",
                        "from citeweave.celery_app import app; "
                        "r=app.control.ping(timeout=3); assert len(r)==1 and list(r[0].values())==[{'ok':'pong'}]",
                    )
                    break
                except RuntimeError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(1)
            report["status"] = "PASS"
        except Exception as exc:
            failure = type(exc).__name__
            report.update(status="FAIL", failure_class=failure, failed_stage=stage[0])
        finally:
            # Only this UUID project's containers/network/new named volumes; never existing project volumes.
            try:
                if cleanup_owned:
                    run("bounded clean shutdown", compose + ["down", "--volumes", "--timeout", "20"], 90)
                    if run("shutdown verification", compose + ["ps", "-a", "-q"]):
                        raise RuntimeError("containers remain after shutdown")
                    for resource in ("volume", "network"):
                        if run(
                            f"{resource} cleanup verification",
                            [
                                "docker",
                                resource,
                                "ls",
                                "-q",
                                "--filter",
                                f"label=com.docker.compose.project={project}",
                            ],
                        ):
                            raise RuntimeError(f"{resource} remains after shutdown")
                    checks.append({"name": "bounded clean shutdown", "status": "PASS"})
                    print("PASS bounded clean shutdown", flush=True)
                else:
                    report["cleanup"] = "NOT_ARMED_NO_RESOURCE_OWNERSHIP"
            except Exception as exc:
                failure = type(exc).__name__
                report.update(status="FAIL", cleanup_failure_class=failure)
            (receipts / "service-smoke.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
        if failure:
            raise SystemExit("Service smoke FAIL (safe summary in .runtime/release/v0.2/service-smoke.json)")
    print("Provider-free service smoke PASS; no ingestion, model inference or generation tested.")


if __name__ == "__main__":
    main()
