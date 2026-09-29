# Public factor evidence

[中文页面](public-factor-evidence.zh-CN.md)

## Purpose of public snapshots

`moneytrees-factor-evidence` generates aggregated Alpha research evidence from a prepared `date, ticker` panel. It checks whether a factor produces a stable and interpretable research signal. It does not replace a full strategy backtest and does not promise future returns.

A snapshot contains:

- factor name and factor family;
- sample interval, trading-day count, observation count, and coverage;
- IC, RankIC, IR, and positive-rate statistics;
- grouped average returns and the number of valid periods;
- data version, code revision, computation configuration, and publication limits.

A snapshot does not contain per-security factor values, tickers, portfolio weights, raw-data paths, credentials, or private model parameters.

## Signal-quality checks

Generate an aggregated quality report together with the snapshot:

```bash
uv run moneytrees-factor-evidence \
  --factor-store /data/moneytree-factor-store/manifest.json \
  --factors all \
  --output /tmp/alpha810-snapshot.json \
  --quality-output /tmp/alpha810-signal-quality.json
```

For the evidence contract shared with formal backtests and Observatory, add:

```bash
  --evidence-v1-output /tmp/factor-evidence.v1.json
```

`factor_evidence.v1` keeps predictive results, uncertainty, risk, residual, temporal-validation, and source information in one aggregated artifact. Diagnostics that were not supplied are marked `not_provided`.

The report checks factor count, coverage, and RankIC availability. `pass` means no gate issue was found, `warn` requires manual review, and `fail` means that no usable factor was available. This is a data and research-quality gate, not a return guarantee.

## Local generation

```bash
uv run moneytrees-factor-evidence \
  --panel /path/to/research-panel.parquet \
  --factors alpha101_001,alpha158_001
```

Use a factor-store manifest when the factors have already been materialized. Keep the resulting JSON aggregated and review its disclosure fields before publication.
