## 1. Shared Factor Storage Utilities

- [x] 1.1 Add shared constants for Alpha101, Alpha191, Alpha158, and Alpha360 factor prefixes.
- [x] 1.2 Add helper functions to identify factor columns and cast only factor columns to a requested dtype.
- [x] 1.3 Validate accepted factor dtype values and provide clear errors for unsupported values.
- [x] 1.4 Add unit tests proving factor dtype coercion changes alpha columns and preserves non-factor column dtypes.

## 2. Short-Term Wide-Panel Dtype Support

- [x] 2.1 Add `--factor-dtype {float32,float64}` to the TuShare CLI with `float32` as the default.
- [x] 2.2 Apply factor dtype coercion after local Alpha158/360 generation and before writing the TuShare output parquet.
- [x] 2.3 Add `--factor-dtype {float32,float64}` to the DolphinDB external-alpha CLI with `float32` as the default.
- [x] 2.4 Apply factor dtype coercion after Alpha101/191 merge and before writing the DolphinDB output parquet.
- [x] 2.5 Record the chosen factor dtype in generated external-alpha manifest metadata.
- [x] 2.6 Update TuShare and DolphinDB CLI tests for default `float32`, explicit `float64`, and wide-panel compatibility.

## 3. Short-Term Factor Selection and Column Pruning

- [x] 3.1 Add backtest config fields for included and excluded factor prefixes or families.
- [x] 3.2 Add CLI/config parsing tests for factor selection settings.
- [x] 3.3 Implement parquet schema inspection using the existing `pyarrow` dependency to resolve selected factor columns before reading data.
- [x] 3.4 Extend `load_market_data` or add a companion loader so parquet inputs can be read with selected columns while pickle inputs remain compatible.
- [x] 3.5 Ensure required non-factor columns for preprocessing, labels, benchmark, tradability filters, and reporting are preserved when column pruning is enabled.
- [x] 3.6 Apply selected factor prefixes before model feature construction so unselected alpha columns cannot enter training.
- [x] 3.7 Report selected prefixes, missing requested prefixes, and final feature counts in backtest output or run metadata.
- [x] 3.8 Add backtest tests covering Alpha158-only selection, missing requested prefixes, and parquet column pruning behavior.

## 4. Documentation and Lightweight Runbooks

- [x] 4.1 Add a storage pressure section to `docs/runbook.md` with rough full-market 810-factor size estimates.
- [x] 4.2 Update `docs/cookbook.md` with lightweight examples for raw cache reuse, subset factor generation, and avoiding unnecessary alpha-all panels.
- [x] 4.3 Update `docs/daily_alpha_research.md` to describe the default factor dtype policy and precision trade-off.
- [x] 4.4 Update `docs/configuration.md` with factor dtype and factor selection configuration fields.
- [x] 4.5 State that raw cache, base panels, factor stores, and experiment artifacts have different retention rules and must not be deleted automatically.

## 5. Medium-Term Factor Store

- [x] 5.1 Define a factor-store manifest schema covering base panel path, factor family paths, row counts, column counts, dtype policy, generation metadata, and key validation status.
- [x] 5.2 Implement validation that base panel and factor-family files have unique, aligned `date, ticker` keys before manifest creation.
- [x] 5.3 Add an additive writer path that can persist a base panel separately from selected factor-family parquet files.
- [x] 5.4 Add an additive loader path that reads a factor-store manifest and joins only requested factor families onto the base panel.
- [x] 5.5 Keep wide-panel parquet generation and loading independent when the factor-store path is not requested.
- [x] 5.6 Add tests for manifest creation, key mismatch failures, selected-family joins, and wide-panel fallback behavior.

## 6. Inspection and Cleanup Guardrails

- [x] 6.1 Add or document a storage inspection workflow that reports disk usage for raw cache, base panels, factor-family data, and experiment artifacts separately.
- [x] 6.2 If a cleanup command is added, make dry-run mode the default and require an explicit option before deleting anything.
- [x] 6.3 Add tests or documented command examples proving inspection does not delete files.

## 7. Verification

- [ ] 7.1 Run `uv run pytest -q tests/test_factors.py tests/test_tushare_data_source.py tests/test_build_dolphindb_alphas_script.py tests/test_external_alphas.py`.
- [ ] 7.2 Run `uv run pytest -q tests/test_backtest_cli.py tests/test_data.py`.
- [ ] 7.3 Run `uv run ruff check .`.
