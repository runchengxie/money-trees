# AGENTS.md

## Project

`money-trees` / Money Trees is an A-share classic-alpha cross-sectional equity research and backtesting toolkit. The current built-in market profile is `cn`. The Python import package remains `moneytree`; prefer the `moneytrees` CLI in new docs while keeping `moneytree` aliases compatible.

The project centers on the Alpha101, Alpha191, Alpha158, and Alpha360 column standard. Alpha158/360 are 518 locally generated features. Alpha101/191 are 292 externally generated columns written to the factor store or merged into the canonical `date, ticker` panel.

## Commands

- Install dev dependencies: `uv sync --dev`
- Install research extras: `uv sync --dev --extra research`
- Run all tests: `uv run pytest -q`
- Run lint: `uv run ruff check .`
- Run CLI smoke: `uv run pytest -q tests/test_smoke.py tests/test_backtest_cli.py`
- Run TuShare data-source tests: `uv run pytest -q tests/test_tushare_data_source.py`
- Run DolphinDB external-alpha tests: `uv run pytest -q tests/test_build_dolphindb_alphas_script.py tests/test_external_alphas.py`
- Run data status/snapshot tests: `uv run pytest -q tests/test_data_status.py tests/test_data_snapshot.py`
- Run factor store tests: `uv run pytest -q tests/test_factor_store.py`
- Run parquet rewrite tests: `uv run pytest -q tests/test_parquet_rewrite_cli.py`
- Run container/runtime tests: `uv run pytest -q tests/test_container_runtime.py`
- Run documentation guard tests: `uv run pytest -q tests/test_docs_inventory.py tests/test_docs_console_scripts.py tests/test_docs_links.py tests/test_docs_style.py`

## Important Paths

- Core package: `src/moneytree/`
- Backtest CLI: `src/moneytree/cli/backtest.py`
- TuShare CLI: `src/moneytree/cli/tushare.py`
- DolphinDB external Alpha CLI: `src/moneytree/cli/dolphindb_alphas.py`
- Data status CLI: `src/moneytree/cli/data_status.py`
- Data snapshot CLI: `src/moneytree/cli/data_snapshot.py`
- Factor store CLI: `src/moneytree/cli/factor_store.py`
- Parquet rewrite CLI: `src/moneytree/cli/parquet_rewrite.py`
- Data quality helpers: `src/moneytree/data_quality.py`
- Configs: `configs/`
- Docs: `docs/`
- Tests: `tests/`
- Maintenance scripts: `project_tools/`

## Project Rules

- Do not commit `.env`, TuShare tokens, local data, raw cache, generated artifacts, or `full_project_source.txt`.
- Keep README as an entry page. Put detailed architecture, data, testing, runbook, and cookbook content in `docs/`.
- Treat `date, ticker` as the canonical panel shape.
- Keep A-share market assumptions in `src/moneytree/markets/cn.py` and `configs/market/cn.yaml`.
- Add or update tests when changing data contracts, output files, model adapters, portfolio logic, config parsing, or TuShare cache behavior.
- Preserve optional dependency behavior: XGBoost, TuShare, DolphinDB, and Optuna should fail with clear messages when their extras are not installed.
- Keep DolphinDB out of core dependencies. Alpha101/191 production must remain an external-alpha path with manifest validation.
- Treat `configs/preset/legacy_notebook_compat.yaml` as a legacy reproduction preset, not the default research path.
- Treat `configs/preset/notebook_compat.yaml` as a transitional compatibility preset.
- Avoid absolute local paths in documentation.
- Keep `market.benchmark_cum_mode` explicit when documenting benchmark cumulative columns.
- Keep `features.missing_feature_policy` defaulting to `error`; use `warn_fill_zero` only for legacy reproduction or migration.

## Data Safety

- `data/`, `artifacts/`, `cache/`, raw TuShare parquet, factor store files, and `manifest.sqlite` are runtime outputs.
- Do not read or print `.env` unless the user explicitly asks for it.
- Do not delete cache, factor store files, data snapshots, or artifacts without explicit user approval.
- Pickle input is allowed only for trusted legacy data. Prefer parquet and `moneytrees-parquet-rewrite` for migration.

## Documentation Terms

- Use `市场配置档` for market profile when writing user-facing Chinese docs, with `market profile` shown on first mention if helpful.
- Use `基准` for benchmark, while keeping column names such as `benchmark_cum_ret` unchanged.
- Use `可交易过滤` for tradability filters.
- Use `冒烟测试` for smoke test.
- Use `预设配置` for preset.
- Use `注册表` for registry.
- Use `面板` consistently in Chinese docs; use `panel` only in code identifiers, file names, or first-mention parentheses.
- Use `因子仓库（factor store）` on first mention, then `因子仓库`.
- Use `原始缓存` for raw cache.
- Use `元数据清单` for manifest unless referring to a file name such as `manifest.json` or `manifest.sqlite`.
- Use `回测产物` for artifacts.
- Use `留出验证` for holdout.
