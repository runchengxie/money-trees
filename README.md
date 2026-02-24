# guan-random-forest-cross-sectional

This project now has a reproducible script-based pipeline in addition to the original notebook.

## Key fixes applied

- Removed hard-coded feature index selection and switched to dynamic `argmax` selection in sequential elimination.
- Fixed rolling backtest logic to avoid mixed segment variables.
- Replaced unstable NAV update denominator (`preds.sum()`) with equal-weight active-position sizing and zero-position guard.
- Removed undefined hedge variable usage from alpha workflow by using explicit regression-based beta/alpha calculation.
- Added transaction cost support (`--cost-bps`) to evaluation and tuning objective.
- Added configurable label source:
  - `actual`: `next_period_return - spy_next_period_return` (default)
  - `pred_rel_return`: legacy behavior
- Added safer missing-value handling (ticker forward-fill + median fill; optional missing indicators).
- Added path-parameterized scripts and optional parquet export.

## Run backtest

```bash
uv run python scripts/run_backtest.py \
  --data data_small.pkl \
  --output-dir artifacts/backtest \
  --feature-selection importance \
  --n-trials 50 \
  --cost-bps 10
```

Outputs:

- `strategy_nav.csv`
- `spy_nav.csv`
- `strategy_vs_spy.csv`
- `metrics.json`
- selected feature lists per segment

## Convert data to parquet

```bash
uv run python scripts/convert_pickle_to_parquet.py --input data_small.pkl
```

