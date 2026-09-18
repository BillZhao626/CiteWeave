"""Flat installed-component SBOM plus lock hashes; no claim of a full image dependency graph."""

import hashlib
import importlib.metadata
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from citeweave.settings import ROOT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    records = {}

    def add(ecosystem, name, version, license_name, scope, source, notices):
        purl = f"pkg:{ecosystem}/{quote(name, safe='/')}@{quote(version)}"
        if purl in records:
            records[purl]["scopes"].append(scope)
            return
        records[purl] = dict(
            name=name,
            version=version,
            purl=purl,
            license=license_name or "NOASSERTION",
            scopes=[scope],
            metadata_source=source,
            notices=notices,
        )

    for scope, folder in [
        ("python-app-dev", ROOT / ".venv/Lib/site-packages"),
        ("python-model", ROOT / ".runtime/ml/Lib/site-packages"),
    ]:
        for dist in importlib.metadata.distributions(path=[str(folder)]):
            meta = dist.metadata
            name, version = meta["Name"], meta["Version"]
            if name == "citeweave-rag":
                continue
            license_name = meta.get("License-Expression")
            if not license_name:
                classifiers = [
                    c.split(" :: ")[-1]
                    for c in meta.get_all("Classifier", [])
                    if c.startswith("License ::") and not c.endswith("OSI Approved")
                ]
                value = meta.get("License", "")
                license_name = " OR ".join(classifiers) or (value.splitlines()[0][:160] if value else "")
            notices = []
            for file in dist.files or []:
                if any(word in Path(str(file)).name.upper() for word in ("LICENSE", "COPYING", "NOTICE")):
                    path = Path(dist.locate_file(file))
                    if path.is_file() and path.stat().st_size < 4_000_000:
                        notices.append(dict(path=str(file).replace("\\", "/"), sha256=digest(path)))
            add(
                "pypi",
                re.sub(r"[-_.]+", "-", name).lower(),
                version,
                license_name,
                scope,
                "installed METADATA and distribution license files",
                notices,
            )

    store = ROOT / "apps/web/node_modules/.pnpm"
    manifests = list(store.glob("*/node_modules/*/package.json")) + list(
        store.glob("*/node_modules/@*/*/package.json")
    )
    for path in manifests:
        package = json.loads(path.read_text(encoding="utf-8"))
        if not package.get("name") or not package.get("version"):
            continue
        license_name = package.get("license") or package.get("licenses") or ""
        if not isinstance(license_name, str):
            license_name = json.dumps(license_name, ensure_ascii=False)
        notices = [
            dict(path=p.name, sha256=digest(p))
            for p in path.parent.iterdir()
            if p.is_file() and any(word in p.name.upper() for word in ("LICENSE", "COPYING", "NOTICE"))
        ]
        add(
            "npm",
            package["name"],
            package["version"],
            license_name,
            "web-build-installed",
            "installed package.json",
            notices,
        )

    components = [
        dict(
            type="library",
            name=r["name"],
            version=r["version"],
            purl=r["purl"],
            **{"bom-ref": r["purl"]},
            licenses=[{"license": {"name": r["license"]}}],
            properties=[dict(name="citeweave:scopes", value=",".join(r["scopes"]))],
        )
        for r in sorted(records.values(), key=lambda r: r["purl"])
    ]
    locks = ["uv.lock", "requirements-worker.lock", "requirements-models.lock", "apps/web/pnpm-lock.yaml"]
    now = datetime.now(timezone.utc).isoformat()
    report = dict(
        at=now,
        scope="Actual installed Python app/dev/model and npm build dependencies; lockfiles retain complete resolution. OS image packages, vendor CUDA libraries and model weights are separately declared in THIRD_PARTY.md.",
        lock_sha256={file: digest(ROOT / file) for file in locks},
        count=len(records),
        unresolved=[r["purl"] for r in records.values() if r["license"] in {"NOASSERTION", "UNKNOWN"}],
        components=list(records.values()),
    )
    output = ROOT / "docs/reports"
    (output / "m3-dependencies.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    sbom = dict(
        bomFormat="CycloneDX",
        specVersion="1.6",
        serialNumber="urn:uuid:" + str(uuid4()),
        version=1,
        metadata=dict(
            timestamp=now, component=dict(type="application", name="CiteWeave", version="M3-candidate")
        ),
        components=components,
    )
    (output / "m3-sbom.cdx.json").write_text(
        json.dumps(sbom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(dict(count=len(records), unresolved=report["unresolved"])))


if __name__ == "__main__":
    main()
