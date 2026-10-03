# Backtest outputs

[Chinese version](https://runchengxie.github.io/money-trees/zh-CN/outputs/)

The output directory is set by `--output-dir` or `output.output_dir`. A normal backtest writes strategy and benchmark NAV, signal diagnostics, metrics, resolved run configuration, and report data.

## Core files

| File | Contents |
| --- | --- |
| `metrics.json` | Strategy, benchmark, risk, turnover, holding-count, IC, and RankIC metrics. |
| `run_config.json` | Resolved configuration, benchmark NAV convention, segment specifications and fit metadata, holdout details, run time, and Git commit. |
| `experiment_manifest.json` | Reproducibility metadata, including input and schema hashes, configuration hash, runtime environment, and data version. |
| `run_summary.txt` | Human-readable backtest summary. |
| `segment_a_features.txt` | Final feature columns used by Segment A. |
| `segment_b_features.txt` | Final feature columns used by Segment B. |

## NAV and returns

| File | Contents |
| --- | --- |
| `strategy_nav.csv` | NAV from portfolio-weight backtesting. |
| `signal_nav.csv` | Diagnostic NAV derived from discrete signals. |
| `benchmark_nav.csv` | Benchmark NAV aligned to strategy evaluation dates. |
| `strategy_returns.csv` | Strategy returns by period. |
| `benchmark_returns.csv` | Benchmark returns by period. |
| `strategy_vs_benchmark.csv` | Combined strategy and benchmark NAV. |

## Diagnostics

| File | Contents |
| --- | --- |
| `signal_profit.csv` | Signal returns, signal turnover, and number of active signal names. |
| `strategy_turnover.csv` | Portfolio turnover. |
| `active_names.csv` | Number of portfolio holdings per period. |
| `ic_series.csv` | IC and RankIC by period. |
| `oos_period_diagnostics.csv` | Out-of-sample returns, turnover, holdings, signal returns, IC, RankIC, target and realized exposures, unallocated exposure, and QP fallback status. |

## Notebook report data

| File | Contents |
| --- | --- |
| `notebook_report_navs.csv` | Strategy, benchmark, signal, and optional hedged NAV. |
| `notebook_rolling_beta.csv` | Rolling beta series. |
| `notebook_residual_returns.csv` | Regression residual returns. |
| `notebook_residual_distribution.csv` | Histogram data for residual returns. |

## Feature-selection outputs

These files are written only when feature-selection history is available:

| File | Contents |
| --- | --- |
| `segment_a_selection_history.csv` | Segment A feature-selection history. |
| `segment_b_selection_history.csv` | Segment B feature-selection history. |
| `segment_a_feature_score_curve.csv` | Segment A feature-count and validation-return curve. |
| `segment_b_feature_score_curve.csv` | Segment B feature-count and validation-return curve. |

## Holdout directory

Setting both `backtest.holdout.start` and `backtest.holdout.end` creates a `holdout/` directory containing:

- `strategy_nav.csv`
- `signal_nav.csv`
- `benchmark_nav.csv`
- `strategy_returns.csv`
- `benchmark_returns.csv`
- `signal_profit.csv`
- `strategy_turnover.csv`
- `active_names.csv`
- `ic_series.csv`
- `oos_period_diagnostics.csv`
- `strategy_vs_benchmark.csv`
- `notebook_report_navs.csv`
- `notebook_rolling_beta.csv`
- `notebook_residual_returns.csv`
- `notebook_residual_distribution.csv`
- `metrics.json`
- `holdout_config.json`

`holdout_config.json` records the model segment, training and validation ranges, and benchmark name used for holdout evaluation.

## `metrics.json`

Main metrics include:

- Total and annualized returns.
- Annualized volatility, maximum drawdown, Sharpe, Sortino, and Calmar ratios.
- 95% VaR and CVaR.
- Benchmark-relative win rate, average excess return, annualized tracking error, and information ratio.
- Alpha, beta, and hedged Sharpe.
- Average, maximum, and annualized turnover.
- Average, minimum, and maximum number of holdings.
- Mean, standard deviation, IR, and positive-value ratio for IC and RankIC.
- Segment A/B validation return, validation turnover, feature count, and best tuning value.

## `run_config.json`

Current metadata includes:

- `resolved_at_utc`
- `git_commit`
- `output_schema_version`
- Parameters resolved from the CLI and configuration files.
- Benchmark name and column mappings, plus `benchmark_cum_mode`.
- Segment A/B training, validation, and rolling-backtest specifications.
- Segment A/B model IDs, validation ranges, feature counts, tuning status, and best tuning values.
- Whether holdout validation is enabled and its date range.
- A `reproducibility` summary with `dataset_version`, input-file hash, schema hash, configuration hash, and the hash of `experiment_manifest.json`.

## `experiment_manifest.json`

The manifest supports experiment reproduction and currently records:

- `manifest_schema_version` and `output_schema_version`.
- Run time, Git commit, random seed, and output directory.
- `dataset_version`, derived from the input-file SHA-256 and raw-input schema hash.
- Input path, file size, modification time, and SHA-256.
- Row and column counts, date ranges, ticker counts, schemas, and schema hashes for the raw input panel and model input panel.
- Configuration paths, each file's SHA-256, the combined configuration-file hash, and the resolved-configuration hash.
- Model ID, training-target column, and model parameters.
- Market-configuration summary.
- Python, platform, and key dependency versions.

Output-file hashes, the version of the TuShare raw-cache manifest, and external data-source versions may be added later.
