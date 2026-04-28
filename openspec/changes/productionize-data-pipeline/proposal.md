## Why

Money Trees already has the core research path for A-share panels, local Alpha158/360 generation, external Alpha101/191 generation, and factor-store loading, but the operational surface is still split across ad hoc checks, wide external-alpha output, and local environment assumptions. This change makes the data pipeline easier to inspect, reproduce, and scale before the full 810-factor workflow becomes the normal path.

The immediate pressure points are data trust and storage shape: users need one read-only status command to understand raw cache, base panel, factor store, and artifacts, and Alpha101/191 should be able to land in the same factor store as Alpha158/360 instead of concentrating IO and memory pressure in a single wide parquet.

## What Changes

- Add a read-only `moneytrees-data-status` CLI for base panel, TuShare raw cache manifest, factor store manifest, and artifact status.
- Extract shared panel sanity rules into a reusable data quality module so TuShare download sanity checks and `moneytrees-data-status` use the same rules.
- Add a DolphinDB Alpha101/191 factor-store output path that writes validated external factor families into `data/factor_store/<market>/`, while keeping the existing wide `--output` path compatible.
- Keep DolphinDB outside core dependencies and outside the main Python runtime image. Add a Python runner `Dockerfile` plus a compose file that runs DolphinDB as a separate service for external Alpha101/191 production.
- Document the operational data layers in `docs/data_status.md`: raw TuShare cache, base panel, factor store, and artifacts.
- Standardize parquet writer options exposed by CLIs, especially `--row-group-size`, while preserving the existing default of `zstd` level 3.
- Do not add destructive cleanup or automatic repair to the first data-status version.
- Do not implement Alpha101/191 formulas locally in Python as part of this change.

## Capabilities

### New Capabilities

- `data-status`: Read-only data status reporting and shared data quality checks for base panels, raw cache manifests, factor-store manifests, and artifacts.
- `external-alpha-factor-store`: Validated Alpha101/191 DolphinDB output can be written directly into the Money Trees factor store with partitioned storage and manifest metadata.
- `containerized-research-runtime`: Docker and compose runtime definitions provide a reproducible Python runner plus separate DolphinDB service without moving DolphinDB into core dependencies.
- `parquet-storage-policy`: Parquet-producing CLIs expose consistent compression, compression-level, and row-group-size controls with documented defaults.

### Modified Capabilities

None.

## Impact

- Affected code:
  - `src/moneytree/data.py`
  - `src/moneytree/data_sources/tushare.py`
  - `src/moneytree/data_quality.py`
  - `src/moneytree/data_status.py`
  - `src/moneytree/cli/data_status.py`
  - `src/moneytree/cli/dolphindb_alphas.py`
  - `src/moneytree/factor_store.py`
  - `src/moneytree/cli/factor_store.py`
  - `src/moneytree/cli/tushare.py`
  - `src/moneytree/cli/parquet_rewrite.py`
  - `pyproject.toml`
- New or updated docs:
  - `docs/data_status.md`
  - `docs/dolphindb_alpha101_191.md`
  - `docs/runbook.md`
  - `README.md`
- New runtime files:
  - `Dockerfile`
  - `.dockerignore`
  - `docker-compose.alpha.yml`
  - optional bootstrap placeholders under `docker/`
- Tests should cover data status summaries, warn/error behavior, TuShare sanity reuse, factor-store external family writes, DolphinDB CLI compatibility, Docker metadata where practical, and parquet option validation.
- Optional dependency behavior must remain intact: DolphinDB, TuShare, XGBoost, and Optuna should still fail with clear messages when their extras are not installed.
- Runtime data, cache, artifacts, `.env`, tokens, and generated parquet files remain outside version control.
