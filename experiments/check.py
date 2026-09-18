"""One entry point for real database + unit checks; exits nonzero on any failure."""

import subprocess
import sys

from common import ROOT, configure

configure()
result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--junitxml=docs/reports/tests.xml"], cwd=ROOT)
sys.exit(result.returncode)
