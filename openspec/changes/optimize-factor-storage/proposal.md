## Why

Full-market Alpha101, Alpha191, Alpha158, and Alpha360 research can produce tens of GB of factor data for a single multi-year panel, and repeated wide-table saves can push local storage into the hundreds of GB. The project needs an explicit storage and loading strategy before the 810-factor workflow becomes the default research path.

## What Changes

- Add a factor storage policy that defaults factor columns to `float32` where safe, while preserving `date, ticker` as the canonical panel key.
- Add CLI/config controls for factor dtype and factor-family/prefix selection so users can run lightweight Alpha158/360 experiments without loading or saving all 810 columns.
- Document expected storage scale, recommended data layout, and which artifacts are durable data versus experiment outputs.
- Add a phased factor-store path that can persist base panel data separately from Alpha101, Alpha191, Alpha158, and Alpha360 family files.
- Add dry-run inspection guidance and follow-up tasks for reporting `data/`, raw cache, factor store, and `artifacts/` disk usage without deleting data by default.
- Keep existing wide-panel parquet workflows working for compatibility.

## Capabilities

### New Capabilities

- `factor-data-management`: Storage, dtype, loading, and documentation behavior for large local and external factor panels.

### Modified Capabilities

- None.

## Impact

- Affected code: `src/moneytree/data.py`, `src/moneytree/factors/qlib.py`, `src/moneytree/cli/tushare.py`, `src/moneytree/cli/dolphindb_alphas.py`, `src/moneytree/config.py`, `src/moneytree/runner.py`.
- Affected docs: `docs/runbook.md`, `docs/cookbook.md`, `docs/daily_alpha_research.md`, and possibly `docs/configuration.md`.
- Affected tests: factor generation dtype tests, TuShare CLI tests, DolphinDB external-alpha tests, backtest config/loading tests, and documentation-adjacent smoke coverage where applicable.
- Dependencies: no new required runtime dependency. DuckDB, Polars, Delta Lake, or LakeFS remain future options and should not be introduced by this change.
