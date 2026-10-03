# Money Trees · Alpha 810 Research

[Chinese version](README.zh-CN.md)

Money Trees is an A-share classic-alpha toolkit for factor computation, validation, and research-evidence production. It covers Alpha101, Alpha191, Alpha158, and Alpha360, with 810 factors in total. The project provides factor-generation entry points, a column-level catalog, a factor store, and baseline evaluation. Full portfolio construction, risk analysis, execution simulation, and backtest jobs belong to `quant-platform` and `quant-backtest-runtime`.

The distribution and documentation name is `money-trees`; the Python import package remains `moneytree`. Prefer the `moneytrees*` command names in new workflows. The older `moneytree*` aliases remain available for compatibility.

## Quick start

Requirements: Python `>=3.10` and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev
```

Run a minimal backtest with a local panel:

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data data_small.parquet \
  --output-dir artifacts/smoke
```

The canonical panel uses `date, ticker`. Parquet is preferred. Pickle input is supported only for trusted legacy data.

## Research paths

1. Run a standard panel backtest using a prepared `date, ticker` dataset.
2. Read published base panels from `quant-market-data-platform` and generate Alpha158/360 locally with `moneytrees-factor-store`. `moneytrees-tushare` is a deprecated compatibility entry point; new data production belongs to the data platform.
3. Extend the factor store with Alpha101/191 using the cross-sectional pure-Python engine (`moneytrees-alpha101-191-python`) or the external DolphinDB workflow (`moneytrees-dolphindb-alphas`). The two generation paths may have different semantics; compare their outputs before using them in formal research.

For larger studies, the factor store avoids maintaining a single persistently wide parquet file.

## Common commands

| Command | Purpose |
| --- | --- |
| `moneytrees` | Run a configured backtest. |
| `moneytrees-tushare` | Deprecated compatibility command for downloading daily TuShare data. Prefer published assets from `quant-market-data-platform`. |
| `moneytrees-factor-store` | Generate local Alpha158/360 factor stores. |
| `moneytrees-alpha101-191-python` | Generate Alpha101/191 with the pure-Python cross-sectional engine. |
| `moneytrees-dolphindb-alphas` | Generate Alpha101/191 through the external DolphinDB path. |
| `moneytrees-factor-mining` | Mine factors from existing factors with genetic algorithms. |
| `moneytrees-data-status` | Read-only inspection of data, factor-store, and backtest-artifact status. |
| `moneytrees-parquet-rewrite` | Rewrite parquet or migrate trusted pickle data. |
| `moneytrees-factor-evidence` | Generate an aggregate public Alpha factor-evidence snapshot. |

The matching `moneytree*` aliases include `moneytree`, `moneytree-tushare`, `moneytree-data-status`, `moneytree-data-snapshot`, `moneytree-data-release`, `moneytree-dolphindb-alphas`, `moneytree-alpha101-191-python`, `moneytree-factor-mining`, `moneytree-factor-store`, `moneytree-parquet-rewrite`, and `moneytree-factor-evidence`. See the [CLI reference](docs/cli-reference.md) for options and safety-sensitive parameters.

Run tests and lint:

```bash
uv run pytest -q
uv run ruff check .
```

## Model adapters

The model registry contains ten adapters: random forest, Extra Trees, Gradient Boosting, HistGradientBoosting, XGBoost classification, XGBoost regression, XGBoost ranking, Ridge, Lasso, and ElasticNet. Classification adapters use the three-class `rel_performance` label. Linear models and XGBoost regression use the continuous `rel_return` label; XGBoost ranking uses pairwise ranking. XGBoost is optional and reports a clear error when its extra is not installed.

## Documentation

The [GitHub Pages documentation](https://runchengxie.github.io/money-trees/) is built from [`docs/index.md`](docs/index.md). Data ingestion, caching, quality governance, versioning, and publication are owned by [`quant-market-data-platform`](https://github.com/runchengxie/quant-market-data-platform); see the [data-platform migration boundary](docs/data-platform-migration.md). Full portfolio construction, risk, execution simulation, and backtest jobs are owned by `quant-platform` and `quant-backtest-runtime`.

- [`docs/index.md`](docs/index.md): project boundary and published documentation entry point.
- [`docs/language-migration-status.md`](docs/language-migration-status.md): English/Chinese page coverage and localization scope.
- [`docs/public-factor-evidence.md`](docs/public-factor-evidence.md), [`docs/publication-audit.md`](docs/publication-audit.md), and [`docs/research-methodology.md`](docs/research-methodology.md): evidence contract, publication controls, and research method.
- [`docs/smoke-test.md`](docs/smoke-test.md): minimal end-to-end run and required panel columns.
- [`docs/architecture.md`](docs/architecture.md): data, market, factor, model, portfolio, backtest, and output layers.
- [`docs/data-contract.md`](docs/data-contract.md): panel index, required and optional columns, labels, and feature semantics.
- [`docs/data-status.md`](docs/data-status.md), [`docs/data-snapshot.md`](docs/data-snapshot.md), and [`docs/data-release.md`](docs/data-release.md): read-only status, metadata snapshots, and release assets.
- [`docs/configuration.md`](docs/configuration.md): configuration layers, merge rules, and fields.
- [`docs/cli-reference.md`](docs/cli-reference.md): `moneytrees*` commands, compatibility aliases, and high-risk options.
- [`docs/outputs.md`](docs/outputs.md), [`docs/cookbook.md`](docs/cookbook.md), and [`docs/runbook.md`](docs/runbook.md): backtest outputs, common research workflows, operations, and troubleshooting.
- [`docs/testing.md`](docs/testing.md): test commands, coverage, and known gaps.
- [`docs/factor-families.md`](docs/factor-families.md) and [`docs/factor-catalog.md`](docs/factor-catalog.md): factor-family provenance and catalog; the machine-readable catalog is [`docs/factor-catalog.csv`](docs/factor-catalog.csv).
- [`docs/classic-alphas-python.md`](docs/classic-alphas-python.md) and [`docs/generate-alpha101-191-with-dolphindb.md`](docs/generate-alpha101-191-with-dolphindb.md): the two Alpha101/191 generation paths.
- [`docs/factor-mining.md`](docs/factor-mining.md) and [`docs/maintenance.md`](docs/maintenance.md): factor mining and repository maintenance.

## Project layout

```text
configs/         Backtest, market, model, and preset configuration
docs/            Usage, architecture, data contracts, and operations
project_tools/   Repository-maintenance tools
scripts/         Compatibility entry points and migration scripts
src/moneytree/   Core package, CLI, data, models, portfolio, and backtest code
tests/           Unit, CLI smoke, and data-source tests
```

## Related project

[guan-random-forest-cross-sectional](https://github.com/runchengxie/guan-random-forest-cross-sectional) is a U.S. equity sibling project using cross-sectional random forests and SPY as its benchmark.

## Current boundaries

- The built-in market profile is `cn`, with `000300.SH` as the default benchmark. Tradability filters and benchmark cumulative-return semantics are documented in [`docs/data-contract.md`](docs/data-contract.md).
- Inputs support parquet and trusted pickle; `date, ticker` parquet is preferred.
- Alpha101/191 can be generated locally in pure Python or externally through DolphinDB. Compare the semantics before formal research; see the generation guides above.
- DolphinDB, TuShare, XGBoost, and Optuna are optional dependencies. A standard panel backtest does not require them all.
- TuShare-derived labels have upstream data-governance limits, including historical ST status, industry history, delisting cases, and survivorship bias. See [`docs/data-contract.md`](docs/data-contract.md).
