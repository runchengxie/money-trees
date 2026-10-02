# Public factor evidence

[中文页面](https://runchengxie.github.io/money-trees/zh-CN/public-factor-evidence/)

## Purpose of public snapshots

`moneytrees-factor-evidence` generates aggregated Alpha research evidence from a prepared `date, ticker` panel. It checks whether a factor produces a stable and interpretable research signal. It does not replace a full strategy backtest and does not promise future returns.

A snapshot contains:

- factor name and factor family;
- sample interval, trading-day count, observation count, and coverage;
- IC, RankIC, IR, and positive-rate statistics;
- grouped average returns and the number of valid periods;
- data version, code revision, computation configuration, and publication limits.

A snapshot does not contain per-security factor values, tickers, portfolio weights, raw-data paths, credentials, or private model parameters.

Schema 1.1 adds `annual_slices`, `regime_slices`, and per-factor `uncertainty`. The snapshot also records `temporal_validation`, global uncertainty metadata, and `multiple_testing`. The unified `factor_evidence.v1` wrapper continues to accept schema 1.0 snapshots.

Annual slices group daily cross-sectional metrics by calendar year. `valid_dates` counts dates with a finite RankIC; annual group means average each day's group return and include that group's valid-period count. These are descriptive subperiod summaries, not independent samples or a validation holdout.

Market regimes are published only when the factor-store base panel includes a realized daily benchmark return series with one consistent value per date. The rule compounds the 252 trading-day benchmark window strictly before each signal date: positive is `bull`, otherwise `bear`. Dates without a complete prior window have no regime label. The forward target column cannot be used as the benchmark. Missing or non-overlapping benchmark inputs produce a `not_provided` status with a reason; annual slices remain available.

## Uncertainty and multiple testing

Pass `--holding-period-days` only when the forward target construction is known:

```bash
uv run moneytrees-factor-evidence \
  --factor-store /data/moneytree-factor-store/manifest.json \
  --factors all \
  --holding-period-days 1 \
  --benchmark-return-column benchmark_daily_return \
  --benchmark-name "CSI 300" \
  --code-revision "$(git rev-parse HEAD)" \
  --output /tmp/alpha810-snapshot.json
```

Pass `--code-revision` to record the source commit in the public snapshot. When `--evidence-v1-output` is also used, the same revision is recorded in its provenance section.

Mean RankIC uncertainty uses Newey–West HAC with Bartlett weights and lag `holding_period_days - 1`, a two-sided standard-normal reference, and a 95% confidence interval. Missing RankIC dates keep their positions in the daily sequence; they do not become zero observations or make distant dates adjacent. The result describes uncertainty in mean daily cross-sectional RankIC, not portfolio returns.

Raw p-values are adjusted with Benjamini–Yekutieli (BY) as the primary false-discovery method. Benjamini–Hochberg (BH) is included as a labeled sensitivity result. The denominator is the full declared factor family; factors with insufficient data remain in the family size but receive no q-value. If the holding period is missing, inferential fields are `not_provided`. Neither raw p-values nor corrected q-values establish tradability or future performance.

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

If the factor store is still inside an unextracted hard-drive archive, use the archive source:

```bash
uv run moneytrees-factor-evidence \
  --factor-store-archive /data/money-tree_20260502_103017.tar \
  --families alpha101,alpha191,alpha158,alpha360 \
  --factors all \
  --date-start 2016-01-01 \
  --date-end 2025-12-31 \
  --data-version cn-factor-store-2016-2025-archive \
  --code-revision "$(git rev-parse HEAD)" \
  --output /tmp/alpha810-2016-2025.json \
  --quality-output /tmp/alpha810-2016-2025-quality.json
```

This copies only the Parquet member currently being read to a temporary file for the reader; it does not unpack the full archive or publish the archive path. The archive must be an uncompressed tar whose manifest, base panel, and four factor families belong to the same release.
