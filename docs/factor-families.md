# Factor families

[Chinese version](https://runchengxie.github.io/money-trees/zh-CN/factor-families/)

Money Trees supports daily A-share Alpha101, Alpha191, Alpha158, and Alpha360 families. This page describes their sources, inputs, generation boundary, and research path. See the [factor column catalog](factor-catalog.md), [data contract](data-contract.md), [TuShare cookbook](cookbook.md), and [runbook](runbook.md) for operational details.

## Research path

```text
TuShare / external daily data
-> standard date,ticker panel
-> Alpha101/191 (local or external) and local Alpha158/360 features
-> feature_lag_periods controls signal availability
-> classification or regression model produces score
-> cn market profile applies tradability filters
-> portfolio construction, rolling backtest, holdout validation, and reports
```

`xgboost_regressor` and linear models train on a continuous target:

```text
rel_return = next_period_return - benchmark_next_period_return
```

Random-forest and XGBoost classification models train on a discrete target:

```text
rel_performance in {-1, 0, 1}
```

The portfolio layer ranks the model score, standardizes it cross-sectionally, and applies portfolio constraints.

## Families

| Family | Source / nature | Typical inputs | Project support |
| --- | --- | --- | --- |
| Alpha101 / WQ101 | WorldQuant 101 Formulaic Alphas. | OHLCV, VWAP, market capitalization, industry | Local Python generation with cross-sectional semantics, or external DolphinDB generation merged into the panel. |
| Alpha191 / GTJA191 | 191 short-horizon price/volume factors from Guotai Junan. | OHLCV, VWAP, and for a few factors index open/close | Local Python generation with cross-sectional semantics, or external DolphinDB generation merged into the panel. |
| Alpha158 | Qlib-style engineered daily features. | Daily OHLCV/VWAP | Built-in 158-column Alpha158-style baseline. |
| Alpha360 | Qlib-style sequence-expanded daily features. | Daily OHLCV/VWAP | Built-in 6-field × 60-lag = 360-column baseline. |

Reference sources:

- WorldQuant 101 / DolphinDB: <https://docs.dolphindb.com/en/Tutorials/wq101alpha.html>
- GTJA191 / DolphinDB: <https://docs.dolphindb.com/zh/modules/gtja191Alpha/191alpha.html>
- Qlib Alpha158/Alpha360: <https://qlib.readthedocs.io/en/latest/component/data.html>

## Generation boundary

The local Python path is maintained in `src/moneytree/factors/classic.py` and uses cross-sectional rank/scale semantics by trading date. The external path uses the repository-provided DolphinDB modules and wrappers. Check source, authorization, version, and module metadata before using external factors in production. Keep the resulting features in the canonical `date, ticker` panel or factor store and record which path generated them.
