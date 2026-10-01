# Generate Alpha101/191 with pure Python

[简体中文](classic-alphas-python.zh-CN.md)

This guide covers the built-in pure-Python Alpha101/191 generators in Money Trees. The implementation was ported from the `wu-alpha191-alpha101` reference repository, but `rank` and `scale` use cross-sectional semantics grouped by trading date. Rolling operators still run over each ticker's time series.

## Background

- The original `wu-alpha191-alpha101` repository provides per-ticker Python implementations of Alpha191/Alpha101. Its `rank` and `scale` operators rank a single ticker's time series, which differs from the standard cross-sectional definition.
- `src/moneytree/factors/classic.py` ports the formulas to the standard `date, ticker` panel. `rank` and `scale` are calculated cross-sectionally by trading date; `ts_*` rolling operators are grouped by ticker.
- The reference repository's README identifies this repository as its successor. The formulas come from public research reports and papers; the port preserves their structure while correcting the calculation semantics.

## Supported fields

| Field | Source column (adjusted by default; raw when using `--raw-price-fields`) | Meaning |
| --- | --- | --- |
| `open` / `high` / `low` / `close` | `open_adj` / `high_adj` / `low_adj` / `close_adj`, falling back to `open` and similar columns | Price fields. |
| `vwap` | `vwap_adj`, falling back to `vwap` | Volume-weighted average price. |
| `volume` | `volume` | Raw volume in shares. |
| `returns` | `pct_change` of `close`, calculated by ticker | Return series. |
| `turnover` | `amount` | Trading amount. |
| `turnover_rate` | `turnover_rate` | If missing, factors that need it return missing values. |
| `cap` | `circ_mv`, falling back to `total_mv` | Market capitalization. |
| `industry` | `industry` | Industry classification. |

`index_open` / `index_close` (also available as `benchmark_open` / `benchmark_close`) remain in the context but are not used by the currently ported formulas.

## Python API

```python
import pandas as pd
from moneytree.factors import build_alpha101_features, build_alpha191_features

panel = pd.read_parquet("data/cn_daily.parquet")
alpha101 = build_alpha101_features(panel)
alpha191 = build_alpha191_features(panel)
```

The functions return DataFrames indexed by `(date, ticker)`, with columns `alpha101_001`…`alpha101_101` and `alpha191_001`…`alpha191_191`. The default dtype is `float32`.

## CLI

Write a compatible wide panel:

```bash
uv run moneytrees-alpha101-191-python \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output data/panel/cn/cn_daily_alpha.parquet \
  --alpha101 \
  --alpha191
```

Write to a factor store:

```bash
uv run moneytrees-alpha101-191-python \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn_daily \
  --no-wide-output \
  --alpha101 \
  --alpha191
```

Common options:

| Option | Description |
| --- | --- |
| `--family` / `--alpha101` / `--alpha191` | Select factor families. |
| `--raw-price-fields` | Use unadjusted price fields. |
| `--factor-dtype` | `float32` (default) or `float64`. |
| `--compression` / `--compression-level` / `--row-group-size` | Parquet write options. |
| `--chunk-trade-dates` | Number of trading dates per factor-store chunk. |
| `--overwrite` | Force recomputation when a factor family with the same name already exists. |
| `--progress` | Report per-factor calculation and chunk-write progress. |

## Differences from the DolphinDB path

- Semantics: the local implementation computes `rank` and `scale` cross-sectionally by trading date. DolphinDB modules also process cross-sections, but null handling, `SMA`/`DECAYLINEAR` boundaries, and price-adjustment conventions may differ.
- Input: the local implementation reads the standard panel directly. The DolphinDB path uploads a `tradetime/securityid` table.
- Resources: the local implementation computes all requested factors in memory. For multi-year, full-market panels on memory-constrained machines, run factor families or date ranges separately, or use the DolphinDB streaming path with `--stream-input auto`.
- Before a full production run, compare a small sample of selected factors against DolphinDB output and confirm the calculation conventions.

## Runtime considerations

Rolling operators such as `ts_rank`, `decay_linear`, and `ts_argmax` use per-ticker `rolling.apply` and can be slow on very large panels. Use `--progress` to monitor progress. For very large production workloads, prefer the DolphinDB path or process date windows in parallel.
