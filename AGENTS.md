# AGENTS.md

## Project

`money-tree` is an A-share cross-sectional equity research and backtesting toolkit. The current built-in market profile is `cn`.

## Commands

- Install dev dependencies: `uv sync --dev`
- Install research extras: `uv sync --dev --extra research`
- Run all tests: `uv run pytest -q`
- Run CLI smoke: `uv run pytest -q tests/test_smoke.py tests/test_backtest_cli.py`
- Run TuShare data-source tests: `uv run pytest -q tests/test_tushare_data_source.py`

## Important Paths

- Core package: `src/moneytree/`
- Backtest CLI: `src/moneytree/cli/backtest.py`
- TuShare CLI: `src/moneytree/cli/tushare.py`
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
- Preserve optional dependency behavior: XGBoost and TuShare should fail with clear messages when their extras are not installed.
- Avoid absolute local paths in documentation.

## Data Safety

- `data/`, `artifacts/`, `cache/`, raw TuShare parquet, and `manifest.sqlite` are runtime outputs.
- Do not read or print `.env` unless the user explicitly asks for it.
- Do not delete cache or artifacts without explicit user approval.

## Documentation Terms

- Use `市场配置档` for market profile when writing user-facing Chinese docs, with `market profile` shown on first mention if helpful.
- Use `基准` for benchmark, while keeping column names such as `benchmark_cum_ret` unchanged.
- Use `可交易过滤` for tradability filters.
- Use `冒烟测试` for smoke test.
- Use `预设配置` for preset.
- Use `注册表` for registry.
- Use `面板` or `panel` consistently inside the same document.
