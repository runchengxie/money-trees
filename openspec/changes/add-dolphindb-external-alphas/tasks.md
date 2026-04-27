## 1. External Alpha Contract

- [x] 1.1 Add `src/moneytree/factors/external.py` with canonical Alpha101 and Alpha191 column generators.
- [x] 1.2 Implement supported external family normalization and clear errors for unsupported families.
- [x] 1.3 Implement `date, ticker` key uniqueness validation for input and external result frames.
- [x] 1.4 Implement requested-family output column validation for missing and unexpected `alpha101_` / `alpha191_` columns.
- [x] 1.5 Implement external alpha merge behavior that preserves the original panel shape and joins generated columns on `date, ticker`.

## 2. Field Mapping and Manifest

- [x] 2.1 Implement DolphinDB input mapping from the standard panel to `tradetime`, `securityid`, OHLCV/VWAP, `cap`, `indclass`, `index_open`, and `index_close`.
- [x] 2.2 Record preferred fields, selected fields, fallback usage, and missing optional fields in a mapping summary.
- [x] 2.3 Implement required-input checks for Alpha101 and Alpha191 before attempting a DolphinDB call.
- [x] 2.4 Build an external factor manifest JSON structure using existing metadata/hash helpers where possible.
- [x] 2.5 Ensure manifest output excludes passwords, `.env` content, TuShare tokens, and other secret values.

## 3. DolphinDB Generation Script

- [x] 3.1 Add optional DolphinDB dependency configuration or documented install path without adding it to core dependencies.
- [x] 3.2 Create `scripts/build_dolphindb_alphas.py` with CLI args for input, output, host, port, user, password, requested families, and module version labels.
- [x] 3.3 Make the script fail clearly when the DolphinDB Python client is not installed.
- [x] 3.4 Implement DolphinDB upload, generation calls, result download, validation, merge, parquet write, and manifest write.
- [x] 3.5 Ensure partial output files are not left behind when validation or generation fails.

## 4. Documentation

- [x] 4.1 Add `docs/dolphindb_alpha101_191.md` documenting the offline producer workflow, field mapping, manifest, and known research risks.
- [x] 4.2 Document the recommended WSL + Docker Desktop + WSL 2 backend setup for a single-node DolphinDB container.
- [x] 4.3 Document expected local DolphinDB module filenames and local mount directories without committing modules or runtime data.
- [x] 4.4 Update `docs/factor_catalog.md` to state clearly that Alpha101/191 are 292 external columns and Alpha158/360 are 518 locally generated columns.
- [x] 4.5 Update cookbook/runbook references with example commands for generating Alpha101/191 and running backtests from the generated parquet.

## 5. Tests and Verification

- [x] 5.1 Add unit tests for canonical column generation and external family validation.
- [x] 5.2 Add unit tests for field mapping, fallback recording, and missing required input errors.
- [x] 5.3 Add unit tests for duplicate key detection, missing alpha column rejection, unexpected alpha column rejection, and merge behavior.
- [x] 5.4 Add unit tests for manifest contents and secret redaction.
- [x] 5.5 Add script-level smoke tests using a mocked DolphinDB session so CI does not require a live DolphinDB server.
- [x] 5.6 Run `uv run pytest -q tests/test_factors.py` and any new external alpha tests.
- [x] 5.7 Run the CLI smoke suite with `uv run pytest -q tests/test_smoke.py tests/test_backtest_cli.py`.
