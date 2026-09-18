"""Copy pinned PDF.js runtime assets without Node fs.cpSync on Windows Unicode paths."""

import shutil

from web_notices import prepare

from citeweave.settings import ROOT

source = ROOT / "apps/web/node_modules/pdfjs-dist"
target = ROOT / "apps/web/public/pdfjs"
for name in ("cmaps", "standard_fonts", "wasm"):
    shutil.copytree(source / name, target / name, dirs_exist_ok=True)
shutil.copyfile(source / "LICENSE", target / "LICENSE")
print("Prepared PDF.js assets and license")
prepare()
