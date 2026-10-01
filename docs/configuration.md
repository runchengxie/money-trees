# Configuration

[简体中文](configuration.zh-CN.md)

`moneytrees` combines YAML, JSON, or TOML files into a run configuration. Keep market, model, backtest, and local preset configuration separate. The older `moneytree` CLI aliases remain available.

Singular compatibility entry points include `moneytree`, `moneytree-tushare`, `moneytree-data-status`, `moneytree-data-snapshot`, `moneytree-data-release`, `moneytree-dolphindb-alphas`, `moneytree-factor-store`, and `moneytree-parquet-rewrite`. Use the corresponding `moneytrees*` entry points in new documentation.

## Default configuration stack

Without `--config`, the CLI reads:

```text
configs/market/cn.yaml
configs/model/rf.yaml
configs/backtest/default.yaml
```

Equivalent command:

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

## Merge rules

Configuration files are deep-merged in the order supplied:

- Later files override earlier values for the same field.
- Mapping fields are merged recursively.
- Non-mapping values are replaced.
- `--data` overrides the configured data path.
- `--output-dir` overrides the configured output directory.
- `--set dotted.path=value` overrides the final configuration.

For example:

```bash
uv run moneytrees \
  --data data_small.parquet \
  --output-dir artifacts/debug \
  --set model.n_trials=0 \
  --set model.feature_selection=none \
  --set backtest.segment1_windows=1 \
  --set backtest.segment2_windows=1
```

`--set` parses booleans, integers, floats, and JSON literals automatically.

## Feature loading

Feature-loading options live under `features`. They select Alpha factor columns when a backtest reads parquet:

```yaml
features:
  include_factor_families: []
  exclude_factor_families: []
  include_factor_prefixes: []
  exclude_factor_prefixes: []
  exclude_factor_columns: []
  missing_feature_policy: error
```

- Factor families can be `alpha101`, `alpha191`, `alpha158`, or `alpha360`; each maps to its column prefix.
- Prefixes match column names directly, for example `alpha158_`.
- `exclude_factor_columns` excludes individual columns, such as an unavailable `alpha191_030`.
- When an `include_*` list is non-empty, only matching Alpha factor columns are selected. Non-factor columns remain available for labels, benchmarks, tradability filters, and reports.
- `exclude_*` removes matching prefixes from the selected Alpha factor columns.
- Parquet input is column-pruned from its schema. Pickle input is read in full before filtering in memory.
- `missing_feature_policy` accepts `error`, `warn_fill_zero`, or `fill_zero`. The default `error` fails if a selected feature is missing. Use `warn_fill_zero` only to reproduce older notebooks.

Example:

```bash
uv run moneytrees \
  --data data/cn_daily_alpha_all.parquet \
  --output-dir artifacts/alpha158-only \
  --set 'features.include_factor_families=["alpha158"]'
```

## Backtest loading and memory

Backtest loading controls live under `backtest`. The default configuration restricts input to the backtest date range and checks memory before reading a factor store:

```yaml
backtest:
  load_mode: auto
  load_warmup_days: 370
  memory_budget_gb: 0.0
  memory_budget_fraction: 0.85
```

- `load_mode` accepts `auto`, `date_range`, or `full`. `auto` currently reads the backtest date range; `full` retains the older full-input path.
- `load_warmup_days` extends the earliest training date backward for feature lags and ticker-level forward filling.
- `memory_budget_gb: 0.0` estimates from system-available memory. A positive value runs preflight against that explicit budget.
- `memory_budget_fraction` sets the share of available memory allowed for this load.
- Preflight does not drop factors, sample stocks, or shorten the training window. If the estimate exceeds the budget, the run fails and suggests reducing load with `features.include_factor_families`, `features.include_factor_prefixes`, or a shorter date range.
- `run_config.json` records `input_load`, including loaded dates, preflight estimates, and selected factor families.

For tree models using the full 810-factor set, explicitly limit factor families or set a memory budget first:

```bash
uv run moneytrees \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/xgb-alpha158 \
  --set 'features.include_factor_families=["alpha158"]' \
  --set backtest.memory_budget_gb=16
```

## Market configuration

File: `configs/market/cn.yaml`.

```yaml
market:
  profile: cn
  benchmark: 000300.SH
  benchmark_return_column: benchmark_next_period_return
  benchmark_cum_column: benchmark_cum_ret
  benchmark_cum_mode: nav
  label_source: actual
  label_threshold: 0.03
  feature_lag_periods: 1
  add_missing_indicators: false
  tradability_columns:
    suspend: is_suspended
    st: is_st
    up_limit: hit_up_limit
    down_limit: hit_down_limit
  tradability_filters:
    suspend: true
    st: true
    up_limit: true
    down_limit: true
```

- `profile` currently supports only `cn`.
- `benchmark_return_column` and `benchmark_cum_column` map upstream column names.
- `benchmark_cum_mode` accepts `nav` or `cumulative_return`; the standard TuShare panel uses `nav`.
- `label_source: actual` creates labels from realized relative returns.
- `label_source: pred_rel_return` uses the `pred_rel_return` column from the input.
- `feature_lag_periods` sets the ticker-level feature lag.

## Model configuration

Model files are under `configs/model/`:

| File | Model ID | Target | Notes |
| --- | --- | --- | --- |
| `rf.yaml` | `random_forest` | `rel_performance` | Main classification path; supports tuning and feature selection. |
| `xgb.yaml` | `xgboost` | `rel_performance` | XGBoost classifier; requires the `xgboost` extra. |
| `xgb_regressor.yaml` | `xgboost_regressor` | `rel_return` | XGBoost regressor; requires the `xgboost` extra. |
| `ridge.yaml` | `ridge` | `rel_return` | Linear regression baseline. |
| `lasso.yaml` | `lasso` | `rel_return` | L1 linear regression baseline. |
| `elasticnet.yaml` | `elasticnet` | `rel_return` | ElasticNet linear regression baseline. |

Common fields:

```yaml
model:
  id: random_forest
  params:
    n_estimators: 300
  feature_selection: importance
  min_features: 2
  max_selection_steps: 200
  n_trials: 0
  tuning_cv_folds: 1
  random_seed: 123
```

Each model adapter validates which tuning and feature-selection modes it supports. Linear models, XGBoost, XGBoost regression, and XGBRanker currently support only `feature_selection: none`. Random forest supports `none`, `importance`, `sequential`, and `notebook_compat`; Extra Trees and gradient boosting support `none`, `importance`, and Optuna tuning; histogram gradient boosting supports only `none`. Tuning is disabled by default. To use Optuna, layer `configs/preset/tuning.yaml` last and install the `tuning` or `research` extra.

## Portfolio configuration

File: `configs/backtest/default.yaml`. Portfolio fields live under `portfolio`:

```yaml
portfolio:
  min_score: 0.05
  winsor_z: 3.0
  weighting_method: heuristic
  gross_target: 1.0
  net_target: 0.0
  max_name_weight: 0.02
  min_names_per_side: 5
  use_vol_scaling: true
  sector_neutral: false
```

`weighting_method` accepts:

- `heuristic`: default heuristic weights.
- `signal_risk_qp`: quadratic-program optimization using signals, covariance, and a turnover penalty.

Related `signal_risk_qp` fields use the `qp_` prefix and include risk aversion, turnover penalty, covariance window, shrinkage estimator, candidate count, and solver parameters.

## Backtest configuration

Backtest fields live under `backtest`:

```yaml
backtest:
  cost_bps: 10.0
  train_months: 60
  gap_months: 3
  test_months: 3
  segment_a:
    train_start: "2004-01-01"
    train_end: "2009-01-01"
    valid_start: "2009-04-01"
    valid_end: "2009-07-01"
  segment_b:
    train_start: "2009-01-01"
    train_end: "2014-01-01"
    valid_start: "2014-04-01"
    valid_end: "2014-07-01"
  segment1_start: "2004-04-01"
  segment1_windows: 60
  segment2_start: "2009-04-01"
  segment2_windows: 20
  holdout:
    start: ""
    end: ""
    model_segment: segment_b
```

- `train_months`, `gap_months`, and `test_months` control rolling-window shape.
- `train_*` and `valid_*` under `segment_a` and `segment_b` define two fixed model-selection and validation periods. Defaults retain the early 2004–2014 setup; data after 2016 requires explicit overrides.
- `segment1_windows` and `segment2_windows` set the number of rolling windows for each segment.
- Holdout validation requires both `start` and `end`.
- `model_segment` accepts `segment_a` or `segment_b`.

## Output configuration

Output fields live under `output`:

```yaml
output:
  output_dir: artifacts/backtest
  export_parquet: ""
```

`output_dir` is the artifact directory. When `export_parquet` is non-empty, the run also saves the preprocessed, filled, and feature-lagged panel. This copies the processed input and can be large for a full 810-factor run; enable it mainly for debugging, audit, or reproduction.

## Factor-generation CLI options

The local TuShare Alpha158/360, pure-Python Alpha101/191, and DolphinDB external Alpha101/191 generators support:

```bash
--factor-dtype float32  # default
--factor-dtype float64  # for precision-sensitive checks
```

This option affects only `alpha101_`, `alpha191_`, `alpha158_`, and `alpha360_` columns. It does not lower precision globally for market data, benchmarks, labels, or tradability filters.

## Presets

Preset files are in `configs/preset/`:

- `template_smoke.yaml`: supplies local `data_path` and `output_dir` values for a smoke run.
- `tuning.yaml`: explicitly enables Optuna tuning for random forest.
- `legacy_notebook_compat.yaml`: reproduces early notebook results using `pred_rel_return`, no feature lag, and notebook-compatible random-forest tuning and feature selection.
- `notebook_compat.yaml`: deprecated transitional compatibility path; it remains readable. Prefer `legacy_notebook_compat.yaml` in new documentation.

Place presets last in the configuration list so they override base configuration.
