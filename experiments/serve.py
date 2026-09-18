"""Local development launcher. Credentials stay server-side; bind loopback only."""

from uuid import NAMESPACE_URL, uuid5

import uvicorn
from common import ROOT, configure

from citeweave.api import create_app

if __name__ == "__main__":
    values = configure()
    app = create_app(values["CW_ADMIN_TOKEN"], uuid5(NAMESPACE_URL, "citeweave-personal-workspace"), ROOT)
    uvicorn.run(app, host="127.0.0.1", port=18080, log_level="warning")
