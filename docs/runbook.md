# Runbook

[中文页面](https://runchengxie.github.io/money-trees/zh-CN/runbook/)

This runbook covers routine execution, troubleshooting, and archival checks. See the [cookbook](cookbook.md) for common examples.

## Operating modes

- Minimal backtest: an existing standard `date, ticker` panel; no TuShare, XGBoost, DolphinDB, or Optuna is required.
- Local 518 factors: TuShare daily data plus local Alpha158/360.
- Complete 810 factors: local Alpha158/360 plus offline DolphinDB Alpha101/191 written to the same factor store.

## Daily sequence

1. Install or update development and research dependencies: `uv sync --dev --extra research`.
2. Refresh the TuShare cache and build the standard panel, or consume a released panel from `quant-market-data-platform`.
3. Build the local factor store when needed.
4. Run the configured backtest and inspect metrics, warnings, and generated metadata.
5. Archive the code revision, configuration, data version, factor-generation path, and output manifest.

Before a complete 810-factor run, verify DolphinDB source authorization and module versions, available memory and disk, the factor manifest, and the expected Alpha101/191 column set. Do not commit raw data, credentials, caches, factor-store files, or backtest artifacts.

## Storage and migration

Use the data-status command for a read-only storage check. Use `moneytrees-parquet-rewrite` for parquet compression or trusted-pickle migration. Full-input DolphinDB uploads can exhaust constrained machines; the default `--stream-input auto` path is safer for parquet `--no-wide-output`, while `--stream-input off` remains available for legacy or wide-output workflows.

## Troubleshooting

Common failures include missing benchmark returns or cumulative columns, missing tradability fields, empty training or validation samples, missing XGBoost/Optuna/DolphinDB dependencies, incomplete Alpha101/191 outputs, and DolphinDB preflight failures or SIGKILL due to memory pressure. Resolve the data contract or optional dependency issue explicitly; do not fill or skip a required field silently.

For each failed run, keep the command, configuration, code revision, input manifest, error output, and whether the failure occurred during data preparation, factor generation, model fitting, validation, or artifact publication. The detailed Chinese page retains the historical command examples and failure-specific checks.
