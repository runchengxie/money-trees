# Smoke test

[Chinese version](https://runchengxie.github.io/money-trees/zh-CN/smoke-test/)

This guide runs the smallest local backtest to confirm that the main A-share workflow executes. See [data-contract.md](data-contract.md) for the full panel contract and [cookbook.md](cookbook.md) for common research workflows.

## 1. Install dependencies

```bash
uv sync --dev
```

## 2. Prepare a small input panel

Parquet is recommended:

```text
data_small.parquet
```

Required columns:

- `date`
- `ticker`
- `next_period_return`
- `benchmark_next_period_return`
- `benchmark_cum_ret`
- `is_suspended`
- `is_st`
- `hit_up_limit`
- `hit_down_limit`

Include at least one numeric or boolean feature column, for example:

```text
f_signal
```

The default configuration converts `date,ticker` to a MultiIndex, generates `rel_return` and `rel_performance`, and trains a model.

## 3. Run the smoke configuration

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data ./data_small.parquet \
  --output-dir ./artifacts/smoke
```

On success, the output includes:

```text
artifacts/smoke/metrics.json
artifacts/smoke/run_config.json
artifacts/smoke/experiment_manifest.json
artifacts/smoke/run_summary.txt
artifacts/smoke/strategy_nav.csv
artifacts/smoke/benchmark_nav.csv
artifacts/smoke/holdout/metrics.json
```

## 4. Use the template preset

`configs/preset/template_smoke.yaml` provides local data and output paths:

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --config configs/preset/template_smoke.yaml
```

The preset reads `./data_small.parquet` by default and writes to `./artifacts/template-smoke`.

## 5. Use the notebook compatibility preset

If the input already contains an externally generated `pred_rel_return`, run:

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --config configs/preset/legacy_notebook_compat.yaml \
  --data ./data_small.parquet \
  --output-dir ./artifacts/notebook-compat
```

This preset uses `pred_rel_return` as the label source and disables the additional feature lag.

## 6. Common failures

- Missing `benchmark_next_period_return`: the default label source needs it to calculate `rel_return`.
- Missing `benchmark_cum_ret`: the backtest cannot build benchmark NAV.
- Missing `is_suspended`, `is_st`, `hit_up_limit`, or `hit_down_limit`: the default `cn` configuration enables tradability filters for these fields.
- Missing feature columns: the model has no training inputs.
- Empty sample: check the date range, filter columns, and `feature_lag_periods`.

## 7. Next steps

1. Adapt `configs/market/cn.yaml` to the upstream data.
2. Confirm that all required columns in [data-contract.md](data-contract.md) are present.
3. Extend the data, factors, and model workflow with examples from [cookbook.md](cookbook.md).
4. Use [runbook.md](runbook.md) for cache handling, troubleshooting, and archive checks.
