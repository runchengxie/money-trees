# CLI reference

[中文页面](cli-reference.zh-CN.md)

Examples use the `moneytrees*` commands. The `moneytree*` aliases remain for compatibility. Data production is no longer the long-term path of this repository; use `quant-market-data-platform` for new data and keep `moneytrees-tushare` for migration and historical reproduction.

## Commands and aliases

| Recommended command | Compatibility alias | Purpose |
| --- | --- | --- |
| `moneytrees` | `moneytree` | Run a configured backtest. |
| `moneytrees-tushare` | `moneytree-tushare` | Build a standard `date, ticker` panel from TuShare. |
| `moneytrees-factor-store` | `moneytree-factor-store` | Build a local Alpha158/360 factor store. |
| `moneytrees-dolphindb-alphas` | `moneytree-dolphindb-alphas` | Generate external Alpha101/191 factors through DolphinDB. |
| `moneytrees-alpha101-191-python` | `moneytree-alpha101-191-python` | Generate Alpha101/191 locally in Python. |
| `moneytrees-factor-mining` | `moneytree-factor-mining` | Mine factors with the genetic-programming workflow. |
| `moneytrees-data-status` | `moneytree-data-status` | Read-only status check for caches, panels, stores, and artifacts. |
| `moneytrees-data-snapshot` | `moneytree-data-snapshot` | Write lightweight metadata snapshots. |
| `moneytrees-data-release` | `moneytree-data-release` | Build GitHub Release-friendly data assets. |
| `moneytrees-parquet-rewrite` | `moneytree-parquet-rewrite` | Rewrite parquet or migrate trusted pickle. |

## Common options

`moneytrees` accepts repeated `--config` files, with later files overriding earlier ones. `--data` overrides the configured panel or factor-store manifest, `--output-dir` overrides the artifact directory, and repeated `--set dotted.path=value` applies a configuration override.

The TuShare command accepts date range, output, benchmark, ticker, factor-family, cache, refresh, proxy, and request-interval options. The compatibility command should not be used as the production data source.

The factor-store, DolphinDB, Python Alpha101/191, mining, status, snapshot, release, and parquet-rewrite commands retain the interfaces documented on the [Chinese reference page](cli-reference.zh-CN.md). Keep optional dependency boundaries intact: XGBoost, TuShare, DolphinDB, and Optuna should report a clear missing-extra error rather than silently changing behavior.
