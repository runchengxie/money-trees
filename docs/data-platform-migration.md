# Data input migration

[Chinese version](https://runchengxie.github.io/money-trees/zh-CN/data-platform-migration/)

## Current primary path

`money-trees` no longer treats data downloads as a long-term responsibility. For formal research, use the `marketdata` command and versioned assets published by [`quant-market-data-platform`](https://github.com/runchengxie/quant-market-data-platform). The platform standardizes and quality-checks those assets; Money Trees consumes them for factor computation and research evidence.

```text
quant-market-data-platform
  ingest TuShare / other sources
  → cache, standardize, govern quality, version, and publish
        ↓ published parquet / data asset
money-trees
  read the date,ticker panel
  → compute Alpha factors
  → calculate IC / RankIC / grouped returns
  → export public evidence snapshots
```

## Compatibility entry points

`moneytrees-tushare` and `moneytree-tushare` remain temporarily available to reproduce older notebooks and migrate historical workflows. They are deprecated compatibility paths, not the new production data entry point. They still require TuShare credentials, maintain a local raw cache, and duplicate standardization responsibilities owned by the data platform.

New research should not place tokens, raw TuShare cache files, or `manifest.sqlite` in Money Trees runtime directories. Prefer versioned parquet or other published data assets from the data platform, then pass them to a backtest or factor CLI as `--data` or panel input.

## Removal conditions

Remove the compatibility entry points and their tests only after all of the following are true:

1. Legacy notebooks that depend on `moneytrees-tushare` have been migrated.
2. The data platform provides all fields and version contracts required by the current A-share panel.
3. Money Trees CI no longer needs the TuShare extra.
4. Release notes provide at least one complete migration example.
