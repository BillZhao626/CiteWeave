# M3 local setup and release rehearsal

Verified target: Windows, PowerShell 7, Python 3.12, Node ≥22.20, pnpm 11.19, Docker Desktop Linux containers, NVIDIA GPU. Development machine: i5-13500H, 16 GB RAM, RTX 4060 Laptop 8 GB. CPU-only and Linux launch scripts are unverified. Package/model downloads require Internet access and several GB of disk space; caches and the generated `.env` are local-only.

```powershell
# Configure your personal DEEPSEEK_API_KEY in the launch environment.
# Do not put it in frontend variables or paste it into logs/issues.
.\scripts\m1.ps1 -Setup
.\scripts\m1.ps1 -Action Up
.\scripts\m1.ps1 -Action Status
.\scripts\m1.ps1 -Action Verify
.\scripts\m1.ps1 -Action Stop
```

The historical script/Compose project names protect existing data volumes. They launch the current M3 application. The API and built UI are at `http://127.0.0.1:18080/`; model gateway 18081, PG 15432, Valkey 16379, Qdrant 16333. Login using the generated `CW_ADMIN_TOKEN` in local `.env`. No usable credentials ship in the source archive. `-Setup -InstallOnly` installs dependencies/models without starting services. `-ProjectName <unique-name>` provides new Docker volumes for isolated rehearsal; ports still need exclusive use.

Setup installs app dependencies from `uv.lock` and frontend packages from `pnpm-lock.yaml`. The complete model lock is split only by source: PyTorch comes from the official CUDA 12.6 wheel index, all other pinned packages from PyPI; `uv pip check` verifies installed dependency compatibility. This avoids CUDA-index shadowing of ordinary packages. E5/BGE downloads use fixed revisions. Existing model process code changes require Stop then Up.

For normal use, create a knowledge base and use the UI's original sample PDF. Ask: “湖畔观测站的温度传感器多久采样一次，原始数据保留多久？” Open the citation, verify page and highlight, then inspect the corresponding run. [API usage](M3_API_USAGE.md) covers automation. Keep one local GPU inference slot and single worker concurrency; a short benchmark is not a sustained-capacity guarantee.

Rebuild, rollback, GC, task recovery and backups retain the [M2 operations contract](M2_OPERATIONS.md). Never manually mark a partial index READY or delete a referenced collection. A document rollback is not a database downgrade. Stop/Up preserves data; no global Docker prune/reset is needed.

```powershell
# Run when no other ingestion/evaluation is active. These create original test data.
.\.venv\Scripts\python.exe scripts/fault_acceptance.py --milestone m3
.\.venv\Scripts\python.exe scripts/backup_restore.py --milestone m3
```

The fault check kills only this project's worker at three durable stages and disables fault injection in finally. Backup briefly quiesces this project's API/worker, saves PG + immutable CAS under `.runtime/backups/<UUID>/`, restores into an isolated database and empty Qdrant, rebuilds every READY version and reparses all historical citations. It never overwrites the main database; backup files remain available for off-machine personal storage. This is not online PITR or disaster recovery certification.

## Source candidate and clean installation

`scripts/public_candidate.py --stage-only` uses an explicit source allowlist and Gitleaks plus an exact active-secret check. It excludes local audits/planning, runtime, caches, third-party PDF originals and dependency binaries. A checked-in exception list contains exact reviewed source/CAS hash lines only; new or changed findings fail. Historical manifests describe their historical files, not the current source.

`scripts/clean_m3.py --prepare` stages a scanned source copy, creates fresh virtual environments/node_modules, and reuses only public model download and package caches. `scripts/clean_m3.py` temporarily stops the main stack, starts a distinct Compose project with new credentials and volumes, proves zero public tables before migration, runs all gates and the original-PDF real-provider smoke test, then stops the rehearsal and restores the main stack. Rehearsal directories/volumes are retained. The state file prevents accidental duplicate rehearsal; after a failed attempt preserve its state/logs before deliberately preparing a new attempt. Same physical Windows machine; this is not a second-host verification.

The final source archive is created by `scripts/public_candidate.py` after required release evidence exists. Use the archive/scanned source directory for a new public repository, not the full local working directory. Remote creation/push is a separate action requiring the owner's target repository and authorization.
