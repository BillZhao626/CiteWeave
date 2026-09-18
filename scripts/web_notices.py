"""Preserve installed frontend dependency license texts in the generated web distribution."""

import hashlib
import json

from citeweave.settings import ROOT


def prepare():
    store = ROOT / "apps/web/node_modules/.pnpm"
    manifests = list(store.glob("*/node_modules/*/package.json")) + list(
        store.glob("*/node_modules/@*/*/package.json")
    )
    packages, texts = {}, {}
    for path in manifests:
        package = json.loads(path.read_text(encoding="utf-8"))
        if not package.get("name") or not package.get("version"):
            continue
        identity = package["name"] + "@" + package["version"]
        references = []
        for file in sorted(path.parent.iterdir()):
            if file.is_file() and any(word in file.name.upper() for word in ("LICENSE", "COPYING", "NOTICE")):
                raw = file.read_bytes()
                key = hashlib.sha256(raw).hexdigest()
                texts[key] = raw.decode("utf-8", errors="replace")
                references.append(key)
        packages[identity] = dict(
            license=package.get("license") or package.get("licenses"),
            source=package.get("repository") or package.get("homepage"),
            texts=references,
        )
    lines = [
        "CiteWeave frontend third-party notices",
        "",
        "Includes installed build tools as well as runtime dependencies. Third-party terms remain unchanged.",
        "No node_modules or third-party binaries are included in the source candidate. Built assets preserve available installed notices below.",
        "",
    ]
    for identity, info in sorted(packages.items()):
        lines.extend([identity, json.dumps(info, ensure_ascii=False), ""])
    for key, value in sorted(texts.items()):
        lines.extend(["LICENSE TEXT SHA-256 " + key, value, ""])
    target = ROOT / "apps/web/public/THIRD_PARTY_NOTICES.txt"
    target.write_text("\n".join(lines), encoding="utf-8")
    print(f"Prepared frontend notices for {len(packages)} installed packages")


if __name__ == "__main__":
    prepare()
