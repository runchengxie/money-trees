# Testing

[Chinese version](https://runchengxie.github.io/money-trees/zh-CN/testing/)

The test suite covers data contracts, configuration parsing, model adapters, portfolio weights, backtest metrics, CLI smoke paths, TuShare normalization, factor stores, data status, snapshots and release assets, external Alpha generation, container files, maintenance scripts, and documentation inventories.

## Commands

Run the full test suite:

```bash
uv run pytest -q
```

Run lint:

```bash
uv run ruff check .
```

Run CLI smoke tests only:

```bash
uv run pytest -q tests/test_smoke.py tests/test_backtest_cli.py
```

Run TuShare source tests:

```bash
uv run pytest -q tests/test_tushare_data_source.py
```

Run mocked DolphinDB external-Alpha tests:

```bash
uv run pytest -q tests/test_build_dolphindb_alphas_script.py tests/test_external_alphas.py
```

Run local Alpha101/191 and factor-mining tests:

```bash
uv run pytest -q tests/test_classic_alphas.py tests/test_mining.py
```

Run portfolio and backtest core tests:

```bash
uv run pytest -q tests/test_portfolio.py tests/test_backtest.py
```

Run data and factor-store CLI tests:

```bash
uv run pytest -q tests/test_data_status.py tests/test_data_snapshot.py tests/test_data_release.py tests/test_factor_store.py tests/test_parquet_rewrite_cli.py
```

Run documentation guard tests:

```bash
uv run pytest -q tests/test_docs_inventory.py tests/test_docs_console_scripts.py tests/test_docs_links.py tests/test_docs_style.py tests/test_legacy_locale_redirects.py
```

The documentation guards check test-file inventory, console-script names, README navigation, local Markdown links, selected style rules, core terminology, high-risk CLI parameter coverage, and factor-catalog status consistency. They do not execute every full command example in the README or docs. Commands requiring a TuShare token, DolphinDB server, large data files, or long runtimes must be validated separately using the runbook.

## Test coverage by file

| Test file | Coverage |
| --- | --- |
| `tests/test_backtest.py` | Rolling windows, performance metrics, benchmark NAV semantics, missing-feature policy, portfolio diagnostics, notebook report data, and OOS result series. |
| `tests/test_backtest_cli.py` | Configuration stack, `--set` overrides, defaults, holdout, output files, run metadata, and invalid arguments. |
| `tests/test_build_dolphindb_alphas_script.py` | DolphinDB Alpha101/191 CLI, compatibility entry point, metadata-manifest sanitization, and optional-dependency errors. |
| `tests/test_classic_alphas.py` | Pure-Python Alpha101/191: column contract, cross-sectional rank semantics, wide-panel CLI output, and factor-store output. |
| `tests/test_container_runtime.py` | Dockerfile, `.dockerignore`, DolphinDB compose configuration, and runtime-output isolation. |
| `tests/test_convert_pickle_to_parquet_script.py` | Deprecated migration of trusted pickle files to parquet and migration notices. |
| `tests/test_data.py` | `date,ticker` index, label creation, missing-feature filling, non-feature column protection, feature lag, and invalid file formats. |
| `tests/test_data_release.py` | Release assets, raw-cache Zstandard round trips and resume validation, local sharding, GitHub CLI preview, and sensitive-file protection. |
| `tests/test_data_snapshot.py` | Snapshot metadata, checksums, README, quality summary, and CLI error paths. |
| `tests/test_data_status.py` | Read-only checks for panels, raw cache, factor stores, and backtest artifacts; JSON output and error/warn modes. |
| `tests/test_data_platform_migration.py` | Documentation contract for the compatibility download path and the primary `quant-market-data-platform` path. |
| `tests/test_docs_console_scripts.py` | `pyproject.toml` console scripts, compatibility aliases, and coverage of high-risk CLI options in README or docs. |
| `tests/test_docs_inventory.py` | Whether every `tests/test_*.py` file is listed in this document. |
| `tests/test_docs_links.py` | Local Markdown links in README and docs, plus README navigation coverage of user documentation. |
| `tests/test_docs_style.py` | High-risk indirect phrasing, core terminology drift, DolphinDB module facts, and factor-catalog consistency in Chinese docs. |
| `tests/test_legacy_locale_redirects.py` | Old Chinese documentation URL redirects and safe generated-page handling. |
| `tests/test_factor_evidence_cli.py` | Public Alpha evidence CLI, file arguments, error paths, and release-field auditing. |
| `tests/test_factor_inference.py` | Newey–West HAC uncertainty and BY/BH multiple-testing corrections. |
| `tests/test_factor_evidence_v1.py` | `factor_evidence.v1` contract and public-field boundaries. |
| `tests/test_factor_publication.py` | Aggregate Alpha evidence schema, annual/regime slices, uncertainty, and public-field boundaries. |
| `tests/test_factor_store_publication.py` | Partitioned/archive Alpha evidence generation, temporal slices, and incremental disclosure-safe output. |
| `tests/test_export_repo_source.py` | Source-export contents and continued exclusion of runtime-data directories. |
| `tests/test_external_alphas.py` | External Alpha101/191 columns, field mappings, input dependencies, merging, and metadata-manifest validation. |
| `tests/test_factor_store.py` | Local and external factor stores, manifests, partitioning, compression, overwrite, and selective loading. |
| `tests/test_factors.py` | Alpha158/360 column counts, local factor extension, factor IC, catalog metadata, and internal factor-operator status. |
| `tests/test_model.py` | Random-forest tuning, time-series CV, feature selection, optional Optuna, and legacy notebook compatibility. |
| `tests/test_mining.py` | GP factor mining: terminal parsing, expression utilities, fitness, report output, and CLI smoke. |
| `tests/test_moneytree_registry.py` | Model and market registries, `cn` benchmark-column mapping, and tradability filters. |
| `tests/test_package_script.py` | `project_tools/package.sh` output paths, inclusion of runtime data, source-only mode, and archive format. |
| `tests/test_public_docs.py` | MkDocs navigation, public-evidence links, and GitHub Pages workflow contract. |
| `tests/test_public_factor_release.py` | End-to-end generation of a sanitized public Alpha snapshot from synthetic data. |
| `tests/test_parquet_rewrite_cli.py` | Parquet/pickle rewriting, compression, row groups, and prevention of in-place overwrite. |
| `tests/test_portfolio.py` | Signal scores, heuristic weights, exposure constraints, volatility scaling, sector neutrality, QP weights, turnover penalty, and fallback diagnostics. |
| `tests/test_project_identity.py` | Distribution identity, `moneytree` import compatibility, and CLI aliases. |
| `tests/test_resources.py` | Memory preflight, parquet-load estimates, and byte formatting. |
| `tests/test_rolling_rank.py` | Alpha rolling-percentile ties, NaN values, `min_periods`, and per-ticker isolation. |
| `tests/test_smoke.py` | End-to-end run using the smoke-test configuration stack. |
| `tests/test_tushare_data_source.py` | TuShare normalization, token, raw cache, `manifest.sqlite` metadata, legacy manifest migration, recent refresh, and latest-name ST tagging. |
| `tests/test_tree_models.py` | Extra Trees, gradient boosting, histogram gradient boosting, and XGBRanker fit/predict and optional-dependency behavior. |

## Optional dependencies

The default development dependencies do not require XGBoost, TuShare, or DolphinDB:

```bash
uv sync --dev
```

XGBoost tests verify clear errors when the dependency is absent. If `xgboost` is already installed, the missing-dependency assertion is skipped. To run XGBoost models:

```bash
uv sync --dev --extra xgboost
```

Real TuShare downloads require:

```bash
uv sync --dev --extra tushare
```

DolphinDB external Alpha101/191 generation requires:

```bash
uv sync --dev --extra external-alphas
```

Optuna tuning requires:

```bash
uv sync --dev --extra tuning
```

## Known test gaps

- Command-example execution: complete CLI examples in README and docs are checked for links and key options but are not all executed individually.
- Output-file hashes: `experiment_manifest.json` records input and configuration hashes; hashes for each CSV/JSON output may be added later.
- Realistic A-share execution: portfolio tests cover weights, exposures, and turnover, but not unfilled orders at price limits, volume capacity, or market impact.
- Historical point-in-time ST and industry classification: tests currently ensure only that latest-name ST tags have explicit semantics.
