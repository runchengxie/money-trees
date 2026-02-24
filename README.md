# guan-random-forest-cross-sectional

Cross-sectional random-forest strategy research project with a script-based, reproducible backtest pipeline.

## Environment setup

- Python: `>=3.10`
- Dependency manager: `uv`

Install dependencies:

```bash
uv sync --dev
```

## Data requirements

Input file can be `.pkl` or `.parquet` and must contain:

- index keys: `date`, `ticker` (either as columns or MultiIndex)
- returns/benchmark columns:
  - `next_period_return`
  - `spy_next_period_return`
  - `spy_cum_ret`
- feature columns: numeric/bool columns except reserved fields listed in `NON_FEATURE_COLUMNS`

The loader normalizes data to a sorted `('date', 'ticker')` MultiIndex.

## Strategy definition and assumptions

- Label source:
  - `actual` (default): `next_period_return - spy_next_period_return`
  - `pred_rel_return`: uses precomputed `pred_rel_return`
- Label mapping (`--label-threshold`, default `0.05`):
  - `> threshold -> +1`
  - `< -threshold -> -1`
  - otherwise `0`
- Position sizing:
  - equal-weight long/short on non-zero predictions
  - zero prediction means no position
- Transaction cost:
  - turnover is estimated as
    - `0.5 * sum_i |w_t,i - w_(t-1),i|`
  - cost deduction per period is `turnover * cost_bps / 10000`

## Leakage handling

Missing-value median fill is now fit on each train window and applied to valid/test windows.

Processing flow:

1. global safe steps: inf-to-NaN, ticker forward-fill, label construction
2. per-window fit/transform:
   - fit medians on train slice
   - apply train medians to train/valid/test slice

This avoids global median leakage from future windows.

## Run backtest

```bash
uv run python scripts/run_backtest.py \
  --data data_small.pkl \
  --output-dir artifacts/backtest \
  --feature-selection importance \
  --n-trials 50 \
  --cost-bps 10
```

## Main parameters

- `--data`: input `.pkl`/`.parquet` path
- `--output-dir`: output folder
- `--label-source`: `actual` or `pred_rel_return`
- `--label-threshold`: label cutoff
- `--add-missing-indicators`: add `__is_missing` numeric indicators
- `--cost-bps`: transaction cost in bps
- `--n-trials`: Optuna trials for RF tuning
- `--feature-selection`: `none` / `importance` / `sequential`
- `--min-features`: floor for sequential selection
- `--max-selection-steps`: cap for sequential selection loop
- `--random-seed`: random seed
- rolling window controls:
  - `--train-months`
  - `--gap-months`
  - `--test-months`
- segment controls:
  - `--segment1-start`, `--segment1-windows`
  - `--segment2-start`, `--segment2-windows`
- `--export-parquet`: optional path to save globally preprocessed parquet

## Outputs

- `strategy_nav.csv`
- `spy_nav.csv`
- `strategy_returns.csv`
- `spy_returns.csv`
- `strategy_vs_spy.csv`
- `metrics.json`
- `segment_a_features.txt`
- `segment_b_features.txt`
- optional selection histories:
  - `segment_a_selection_history.csv`
  - `segment_b_selection_history.csv`

## Metrics definition (`metrics.json`)

- `strategy_total_return`: final strategy NAV minus 1
- `spy_total_return`: final SPY NAV minus 1
- `strategy_sharpe`: mean/std of strategy period returns
- `spy_sharpe`: mean/std of SPY period returns
- `alpha`, `beta`: OLS regression of strategy returns on SPY returns
- `information_ratio`: mean/std of regression residual returns
- `hedged_sharpe`: Sharpe of beta-hedged returns (`strategy_ret - beta * spy_ret`)

## Notes and current limitations

- Backtest period timestamp now uses the real last date in each test slice (not calendar `test_end` fallback unless needed).
- `active_names` is counted by unique `ticker` with non-zero signals.
- Turnover is estimated from name-level weights; it is a practical approximation, not a full order-level execution model.
- Scripts currently use local `src` path injection for direct execution (`scripts/*.py`).

## Convert pickle to parquet

```bash
uv run python scripts/convert_pickle_to_parquet.py --input data_small.pkl
```
