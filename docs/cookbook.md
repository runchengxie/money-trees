# Cookbook

[简体中文](cookbook.zh-CN.md)

This cookbook collects reproducible workflows and focuses on how to use the tools. The [runbook](runbook.md) covers routine operations, recovery, and archive checks.

## 1. Run a minimal local backtest

Prepare a parquet file that follows the [data contract](data-contract.md):

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data data_small.parquet \
  --output-dir artifacts/smoke
```

For debugging, reduce rolling windows and leave tuning disabled:

```bash
uv run moneytrees \
  --data data_small.parquet \
  --output-dir artifacts/debug \
  --set model.feature_selection=none \
  --set model.n_trials=0 \
  --set backtest.segment1_windows=1 \
  --set backtest.segment2_windows=1
```

## 2. Download a daily panel with the legacy TuShare compatibility CLI

The TuShare commands in this section are for reproducing older notebooks and migrating historical workflows. For new production data, use versioned assets published by `quant-market-data-platform`; see [data input migration](data-platform-migration.md).

Install research dependencies and set a TuShare token:

```bash
uv sync --dev --extra research
export TUSHARE_TOKEN=your_token
```

Download daily data:

```bash
uv run moneytrees-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --progress \
  --benchmark 000300.SH
```

`--cache-dir` caches raw responses for `daily`, `daily_basic`, `adj_factor`, `stk_limit`, and `suspend_d`. Repeated downloads of the same date range reuse locally cached parquet for dates already present. For long, full-market downloads, use `--progress` to monitor trading-date progress by API, cumulative rows, cache hits, and actual request counts.

After creating the base panel, run a read-only quality check:

```bash
uv run moneytrees-data-status \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --raw-cache data/raw/tushare \
  --mode warn
```

This streams through the parquet panel to check `date,ticker`, key-column nulls, derived-return consistency, adjusted-price consistency, and raw-cache dates where `daily` has rows but `adj_factor` or `daily_basic` is empty. Return columns allow only natural boundary nulls: the first and last row per ticker and the first and last benchmark trading dates.

## 3. Build a local Alpha158/360 factor store from a compatibility-path panel

This section continues from the TuShare compatibility path and is intended for reproducing older workflows. New research should prefer a standard panel published by the data platform.

Fetch the base panel:

```bash
uv run moneytrees-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/panel/cn/cn_daily_raw.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --progress \
  --benchmark 000300.SH \
  --sanity-check warn
```

Then generate only the factor families needed. The factor store keeps the base panel and factor families separate instead of writing every column into one very wide parquet file.

Missing selected features cause an error by default. During migration of older data, you can temporarily set:

```bash
uv run moneytrees \
  --data data/factor_store/cn_daily/manifest.json \
  --set features.missing_feature_policy=warn_fill_zero
```

Generate a factor family:

```bash
uv run moneytrees-factor-store \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output-dir data/factor_store/cn_daily \
  --factor-family alpha158 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --progress
```

Local Alpha features use adjusted prices by default and store `alpha158_` and `alpha360_` columns as `float32`. Pass `--factor-dtype float64` to retain double precision. To use unadjusted prices:

```bash
uv run moneytrees-factor-store \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output-dir data/factor_store/cn_daily_raw_factor \
  --factor-family alpha158 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --progress \
  --raw-features
```

For parquet input, `moneytrees-factor-store` reads partitions by `--chunk-trade-dates` and includes the historical overlap needed by Alpha158/360. On memory-constrained machines, reduce the chunk size to `20` or `10` rather than merging factors back into a wide parquet. `--raw-features` changes only the price basis for local Alpha158/360 generation; it does not reduce TuShare API downloads.

Use the factor-store manifest as a backtest input and select the families to load:

```bash
uv run moneytrees \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/ridge-alpha158-only \
  --set 'features.include_factor_families=["alpha158"]'
```

For a lightweight debug run, generate only Alpha158:

```bash
uv run moneytrees-factor-store \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output-dir data/factor_store/debug_alpha158 \
  --factor-family alpha158 \
  --chunk-trade-dates 20 \
  --progress
```

## 4. Add Alpha101/191 (292 columns)

There are two generation paths:

1. Local pure Python, using cross-sectional semantics: `moneytrees-alpha101-191-python`. It is suitable for learning and small-scale research; see [classic-alphas-python.md](classic-alphas-python.md).
2. External DolphinDB generation, recommended for production: generate offline and write into the same factor store. See [generate-alpha101-191-with-dolphindb.md](generate-alpha101-191-with-dolphindb.md) for environment and calculation details.

With parquet input and `--no-wide-output`, the DolphinDB CLI defaults to `--stream-input auto`: it reads, uploads, computes, and writes data in target-date and warmup-window chunks. Wide output or explicit `--stream-input off` still uploads the full input. First run a small smoke test for `--alpha101` and `--alpha191` separately; for full generation, prefer separate runs by factor family.

Install the external-Alpha dependencies:

```bash
uv sync --dev --extra external-alphas
```

Generate both families and write them to the factor store:

```bash
uv run moneytrees-dolphindb-alphas \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn_daily \
  --no-wide-output \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --alpha101 \
  --alpha191 \
  --factor-dtype float32 \
  --stream-input auto \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

For the older wide-panel path, pass `--output data/cn_daily_alpha_all.parquet`. The factor-store manifest is written to:

```text
data/factor_store/cn_daily/manifest.json
```

## 5. Run XGBoost regression with the full 810-factor store

```bash
uv sync --dev --extra research

uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/xgb-alpha-all \
  --set backtest.memory_budget_gb=32
```

`xgb_regressor` predicts continuous `rel_return` scores, which then enter portfolio construction. The default `backtest.load_mode: auto` reads only the backtest date range and runs a memory preflight before loading a factor store. If the full 810-factor estimate exceeds the budget, split the run by factor family instead of forcing `backtest.load_mode=full`.

To debug a model with one factor family, avoid loading all 810 factors:

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/ridge.yaml \
  --config configs/backtest/default.yaml \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/ridge-alpha158-only \
  --set 'features.include_factor_families=["alpha158"]'
```

You can also select a prefix:

```bash
uv run moneytrees \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/debug-alpha360 \
  --set 'features.include_factor_prefixes=["alpha360_"]' \
  --set model.feature_selection=none \
  --set model.n_trials=0
```

## 6. Diagnose single-factor IC / RankIC

```python
import pandas as pd
from moneytree.factor_store import load_factor_store
from moneytree.factors import compute_factor_ic, summarize_factor_ic

frame = load_factor_store(
    "data/factor_store/cn_daily/manifest.json",
    include_factor_families=["alpha158"],
)
ic = compute_factor_ic(frame, ["alpha158_kmid", "alpha158_roc_20"])
summary = summarize_factor_ic(ic)
print(summary)
```

`compute_factor_ic` uses `next_period_return` by default and calculates cross-sectional IC and RankIC by date.

## 7. Switch to a linear-model baseline

Ridge:

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/ridge.yaml \
  --config configs/backtest/default.yaml \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/ridge-alpha-daily
```

For Lasso or ElasticNet, replace the model config with:

```text
configs/model/lasso.yaml
configs/model/elasticnet.yaml
```

Linear models predict `rel_return` and currently do not support tuning or feature selection.

## 8. Explicitly enable random-forest tuning

Model tuning is disabled by default. To use Optuna, add the tuning preset:

```bash
uv sync --dev --extra tuning

uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --config configs/preset/tuning.yaml \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/rf-alpha-all-tuned
```

## 9. Use signal-risk QP portfolio weighting

The default portfolio method is `heuristic`. To use QP:

```bash
uv run moneytrees \
  --data data_small.parquet \
  --output-dir artifacts/qp \
  --set portfolio.weighting_method=signal_risk_qp \
  --set portfolio.qp_turnover_penalty=10 \
  --set portfolio.qp_risk_aversion=20
```

QP estimates covariance from `next_period_return` in the training window. If the solver fails, it falls back to heuristic weights by default.

## 10. Run final holdout validation

```bash
uv run moneytrees \
  --data data_small.parquet \
  --output-dir artifacts/holdout-check \
  --set backtest.holdout.start=2015-01-01 \
  --set backtest.holdout.end=2015-12-31 \
  --set backtest.holdout.model_segment=segment_b
```

Holdout results are written to:

```text
artifacts/holdout-check/holdout/
```

## 11. Use the local template preset

`configs/preset/template_smoke.yaml` sets local paths:

```yaml
market:
  data_path: ./data_small.parquet

output:
  output_dir: ./artifacts/template-smoke
```

Run it with:

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --config configs/preset/template_smoke.yaml
```

## 12. Migrate legacy pickle data

`scripts/convert_pickle_to_parquet.py` is a deprecated compatibility tool, not the primary research path. Prefer `moneytrees-parquet-rewrite`:

```bash
uv run moneytrees-parquet-rewrite \
  --input data_small.pkl \
  --output data_small.parquet
```

The older script remains available for simple migration of trusted pickle files:

```bash
uv run python scripts/convert_pickle_to_parquet.py \
  --input data_small.pkl
```

## 13. Reproduce a legacy notebook

`configs/preset/legacy_notebook_compat.yaml` is only for reproducing early notebook results. Do not use it for formal Alpha101/191/158/360 research. It:

- Uses `pred_rel_return` as the label source.
- Sets `feature_lag_periods` to `0`.
- Uses the `notebook_compat` feature-selection path.
- Sets trading costs to `0`.
- Enables 200 random-forest tuning trials.

Run it with:

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --config configs/preset/legacy_notebook_compat.yaml \
  --data data_small.parquet \
  --output-dir artifacts/legacy-notebook-compat
```

The input must contain `pred_rel_return`.
