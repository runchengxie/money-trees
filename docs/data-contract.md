# Data contract

[中文页面](https://runchengxie.github.io/money-trees/zh-CN/data-contract/)

This page defines the data shape, required columns, optional columns, and label semantics used by Money Trees backtests.

## File format and index

`moneytrees` accepts `.pkl`, `.pickle`, and `.parquet` inputs. Parquet is preferred. Pickle is only for trusted legacy research data; migrate it with:

```bash
uv run moneytrees-parquet-rewrite --input data/old.pkl --output data/old.parquet
```

The canonical index is `date, ticker`. Input files may provide ordinary columns; runtime code calls `ensure_date_ticker_index` and sorts by `date, ticker`.

## Minimum contract

The default `configs/market/cn.yaml` uses `label_source: actual`. A usable panel must provide the date/ticker keys, the configured label columns, and the feature columns selected by the model configuration. Benchmark-relative labels use:

```text
rel_return = next_period_return - benchmark_next_period_return
```

Classification models use `rel_performance` in `{-1, 0, 1}`. Regression models use continuous `rel_return`; `xgb_ranker` uses pairwise ranking labels.

## Features and timing

Feature selection follows the configured factor family and model settings. `feature_lag_periods` defaults to `1`, so a signal observed after the T-day close is not used until the next period. Keep feature cutoffs, label intervals, prediction horizon, purge window, and embargo in the research record.

## Missing values and benchmark semantics

The default `features.missing_feature_policy` is `error`. Use `warn_fill_zero` only for legacy reproduction or migration. Keep `market.benchmark_cum_mode` explicit when documenting benchmark cumulative columns. Missing benchmark returns, tradability fields, or required labels should fail validation rather than silently change the sample.

## TuShare panels and price conventions

The TuShare compatibility entry point produces the standard `date, ticker` panel. New data production belongs to `quant-market-data-platform`; `moneytrees-tushare` remains for migration and historical reproduction. Adjusted price fields are preferred for factor calculations, while raw volume remains raw volume. Keep VWAP and adjustment choices explicit in the generated metadata.

For the complete column list and factor-specific rules, see the [factor catalog](factor-catalog.md) and [factor families](factor-families.md). The Chinese page remains the detailed historical reference for fields and examples.
