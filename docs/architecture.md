# Architecture

[Chinese version](https://runchengxie.github.io/money-trees/zh-CN/architecture/)

Money Trees is an A-share classic-alpha computation and aggregated-evidence toolkit. Its long-term boundary is the 810-factor contract, the data contract, and the public evidence export. Full portfolio construction, risk, execution simulation, and formal backtests are owned by `quant-platform` and `quant-backtest-runtime`.

## Data flow

```text
TuShare / external data
-> standard date,ticker panel
-> market-profile validation and tradability filters
-> factor generation or merge
-> feature lag
-> model adapter training
-> portfolio weights
-> rolling backtest and holdout validation
-> metrics, CSV, JSON, and report artifacts
```

The default configuration stack is `configs/market/cn.yaml`, `configs/model/rf.yaml`, and `configs/backtest/default.yaml`.

## Layers

- Data layer: reads trusted pickle or parquet, normalizes `date, ticker`, creates `rel_return` and `rel_performance`, handles missing values and feature lag, and stores TuShare cache partitions.
- Market layer: keeps A-share assumptions in `src/moneytree/markets/cn.py` and `configs/market/cn.yaml`, including benchmark, tradability filters, limits, and return conventions.
- Factor layer: provides local Alpha158/360 generation and the local cross-sectional Alpha101/191 path. DolphinDB Alpha101/191 modules remain an external production path.
- Model layer: registers seven tree adapters and three linear baselines. Optional XGBoost and other extras must fail with a clear message when unavailable.
- Portfolio and backtest layers: consume model scores, apply ranking and constraints, and produce research artifacts. These layers are not a replacement for the formal shared implementation in the platform repositories.
- Evidence layer: `moneytrees-factor-evidence` emits aggregated factor evidence and `factor_evidence.v1` artifacts without per-security values or private paths.

## Storage

Runtime data belongs under local `data/`, `artifacts/`, and `cache/` locations and must not be committed. Factor stores use manifests and partitioned data; record data version, code revision, configuration, and generation path. Public repositories may contain reviewed static JSON and documentation only.
