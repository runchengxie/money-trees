## 1. Correctness Tests

- [x] 1.1 Add a `preprocess_data` test proving missing future returns, benchmark returns, tradability flags, ST flags, suspension flags, and limit flags are not forward filled.
- [x] 1.2 Add benchmark NAV tests for `nav` mode and `cumulative_return` mode, including an index-like series such as `100, 110, 121`.
- [x] 1.3 Add metrics tests proving total return uses complete period returns when `strategy_returns` and `benchmark_returns` are provided.
- [x] 1.4 Add rolling backtest and holdout tests for default `missing_feature_policy=error`.
- [x] 1.5 Add legacy compatibility tests for `missing_feature_policy=warn_fill_zero` or `fill_zero`.
- [x] 1.6 Add a TuShare test covering the latest-name ST warning, metadata, or renamed flag behavior.
- [x] 1.7 Add portfolio diagnostics tests for realized gross, realized net, unallocated exposure, and QP fallback recording.
- [x] 1.8 Add run output tests that record segment validation periods, selected feature counts, model id, tuning status, and holdout segment provenance.

## 2. Correctness Implementation

- [x] 2.1 Refactor `preprocess_data()` so target, label, benchmark, prediction output, and tradability/state columns are excluded from ticker-level forward fill.
- [x] 2.2 Add an internal helper or constant set for non-feature columns shared by preprocessing, feature selection, and tests.
- [x] 2.3 Add `benchmark_cum_mode` to market settings and `configs/market/cn.yaml`, with validation for supported values.
- [x] 2.4 Update `build_benchmark_nav()` to normalize benchmark input according to the explicit benchmark mode.
- [x] 2.5 Update all `build_benchmark_nav()` call sites to pass the resolved benchmark mode and record it in run config or summary output.
- [x] 2.6 Update `compute_performance_metrics()` to compute total and annualized returns from aligned period return series when present.
- [x] 2.7 Add `missing_feature_policy` to config parsing and defaults, with `error` as the normal default.
- [x] 2.8 Replace rolling and holdout silent feature zero-fill with a shared missing-feature policy helper.
- [x] 2.9 Configure legacy notebook compatibility to use the explicit warning/fill policy needed for old data.
- [x] 2.10 Update TuShare stock-basic merge behavior so latest-name ST semantics are explicit through metadata, warning text, or a clearer column name.
- [x] 2.11 Add per-period portfolio diagnostics for target/realized exposure and QP fallback status.
- [x] 2.12 Persist new diagnostics in CSV/JSON outputs without changing existing public filenames.
- [x] 2.13 Record validation and tuning period metadata in run output and holdout output.

## 3. Documentation Updates

- [x] 3.1 Remove the README lyric quote and replace it with an original project summary.
- [x] 3.2 Update README quick paths to distinguish standard panel, factor store, and full 810-factor workflows.
- [x] 3.3 Add README command examples for `moneytrees-data-status`, `moneytrees-data-snapshot`, `moneytrees-factor-store`, and `moneytrees-parquet-rewrite`.
- [x] 3.4 Add README notes for DolphinDB container setup, trusted pickle input, and preferred parquet migration.
- [x] 3.5 Update AGENTS.md with data status, data snapshot, factor store, parquet rewrite, data quality paths, and focused test commands.
- [x] 3.6 Update docs/testing.md to include every current `tests/test_*.py` file and focused commands for newer engineering tests.
- [x] 3.7 Rewrite docs/data_snapshot.md in Chinese and add a `--note` example.
- [x] 3.8 Update docs/architecture.md so factor store is listed as a first-class data/factor module.
- [x] 3.9 Update docs/maintenance.md to include `src/moneytree/factor_store.py` and facade-preserving split guidance.
- [x] 3.10 Update docs/data_contract.md, docs/runbook.md, and docs/cookbook.md for benchmark mode, missing feature policy, trusted pickle migration, and latest-name ST semantics.
- [x] 3.11 Normalize user-facing terminology for 面板, 因子仓库, 原始缓存, 元数据清单, 回测产物, 留出验证, 冒烟测试, 市场配置档, 基准, and 可交易过滤.
- [x] 3.12 Replace avoidable indirect contrast phrasing in README/docs with direct statements.

## 4. Documentation Guard Tests

- [x] 4.1 Add `tests/test_docs_inventory.py` to ensure every `tests/test_*.py` file appears in docs/testing.md.
- [x] 4.2 Add `tests/test_docs_console_scripts.py` to ensure each console script in pyproject.toml is documented in README or docs.
- [x] 4.3 Add `tests/test_docs_links.py` to validate local Markdown links in README.md and docs.
- [x] 4.4 Add `tests/test_docs_style.py` with a small allowlist-friendly check for avoidable indirect Chinese patterns and terminology drift.
- [x] 4.5 Update tests when a compatibility script or hidden internal command is intentionally excluded from public docs.

## 5. Maintenance And Quality Gates

- [x] 5.1 Expand Ruff lint selection in a small first batch, starting with import sorting, pyupgrade, and bugbear rules.
- [x] 5.2 Apply only the mechanical code changes required by the new Ruff rules.
- [x] 5.3 Update docs/maintenance.md with a staged split plan for `runner.py`, `factor_store.py`, `backtest.py`, `portfolio.py`, `model.py`, and `data_sources/tushare.py`.
- [x] 5.4 Add or update tests that protect public behavior before any large module split starts.
- [x] 5.5 Document the compatibility lifecycle for `moneytree` and `moneytrees` CLI aliases.
- [x] 5.6 Document the compatibility role of `scripts/build_dolphindb_alphas.py`, `scripts/convert_pickle_to_parquet.py`, and `configs/preset/notebook_compat.yaml`.

## 6. Verification

- [x] 6.1 Run `uv run ruff check .`.
- [x] 6.2 Run `uv run pytest -q tests/test_data.py tests/test_backtest.py tests/test_backtest_cli.py tests/test_tushare_data_source.py tests/test_portfolio.py`.
- [x] 6.3 Run `uv run pytest -q tests/test_docs_inventory.py tests/test_docs_console_scripts.py tests/test_docs_links.py tests/test_docs_style.py`.
- [x] 6.4 Run `uv run pytest -q tests/test_data_status.py tests/test_data_snapshot.py tests/test_factor_store.py tests/test_parquet_rewrite_cli.py tests/test_container_runtime.py`.
- [x] 6.5 Run `uv run pytest -q` after focused tests pass.
- [x] 6.6 Run `openspec status --change audit-project-maintainability` and confirm the change is apply-ready.
