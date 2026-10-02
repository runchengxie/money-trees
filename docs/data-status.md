# Data status checks

[简体中文](https://runchengxie.github.io/money-trees/zh-CN/data-status/)

This guide describes Money Trees data layers, the status-check command, and storage practices. The README links to the entry points; daily troubleshooting, coverage checks, and storage estimates are documented here.

## Data layers

Keep runtime data in four layers:

```text
data/raw/tushare/        Raw TuShare API cache; can be used to rebuild the base panel
data/panel/cn/           Clean base date,ticker panel without a large set of factors
data/factor_store/cn/    Alpha101/191/158/360 factor store partitioned by family and date chunk
artifacts/               Backtest outputs retained by experiment or cleaned up on a short lifecycle
```

The standard panel key is `date, ticker`. The market profile remains defined by `configs/market/cn.yaml` and `src/moneytree/markets/cn.py`; the default benchmark is `000300.SH`.

## Inspect current coverage

`moneytrees-data-status` is read-only. It does not delete, refresh, repair, or rewrite files.

Check a base panel. Parquet panels use streaming, narrow-column checks so a multi-year, full-market panel is not loaded completely into pandas just for a status report:

```bash
uv run moneytrees-data-status \
  --panel data/panel/cn/cn_daily_2016_2025.parquet \
  --format text \
  --mode warn
```

Check a raw TuShare cache:

```bash
uv run moneytrees-data-status \
  --raw-cache data/raw/tushare \
  --format text
```

Check a factor store:

```bash
uv run moneytrees-data-status \
  --factor-store data/factor_store/cn/manifest.json \
  --format text
```

A full factor-store quality check scans every factor value in every partition. Skip value scans when you only need a quick metadata check, or scan one factor family to investigate it:

```bash
uv run moneytrees-data-status \
  --factor-store data/factor_store/cn/manifest.json \
  --skip-factor-quality

uv run moneytrees-data-status \
  --factor-store data/factor_store/cn/manifest.json \
  --factor-family alpha191 \
  --progress
```

Use `--allow-factor-column` to allow known unavailable or definitionally constant columns and focus the report on new anomalies. For example, `alpha191_030` depends on external `MKT/SMB/HML` inputs. Alpha360 lag-0 relative-change columns are zero by definition:

```bash
uv run moneytrees-data-status \
  --factor-store data/factor_store/cn/manifest.json \
  --allow-factor-column alpha191_030 \
  --allow-factor-column alpha360_close_lag00,alpha360_volume_lag00 \
  --mode error
```

Check backtest artifacts:

```bash
uv run moneytrees-data-status \
  --artifacts artifacts/xgb-alpha-all \
  --format text
```

Check all four layers once and emit JSON for CI:

```bash
uv run moneytrees-data-status \
  --panel data/panel/cn/cn_daily_2016_2025.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn/manifest.json \
  --artifacts artifacts/xgb-alpha-all \
  --format json \
  --mode error
```

`--mode warn` reports data errors without returning a failure exit code. `--mode error` returns nonzero when data errors are found. Invalid arguments and unreadable inputs still fail. The command remains read-only: it never refreshes the raw cache, repairs a panel, or rewrites a factor store or backtest artifact.

## Checks performed

Base panel:

- File size, row count, column count, date range, trading-day count, and ticker count.
- Duplicate `date, ticker` keys and missing required columns.
- Missing counts and rates for key columns.
- Non-positive raw or adjusted prices, negative volume, and `high < low`.
- Parquet scans use streaming, narrow columns. If `date, ticker` is not sorted, the report flags the order and uses a narrow-column fallback to count duplicate keys exactly.
- Derived-return consistency. The checker recomputes `return_1d`, `next_period_return`, `benchmark_return`, and `benchmark_next_period_return` from `close_adj` (falling back to `close`) and `benchmark_close`.
- Natural boundary nulls are allowed: the first `return_1d` and last `next_period_return` for each ticker, plus the global first `benchmark_return` and last `benchmark_next_period_return`.
- Adjusted-price consistency. When `adj_factor` and `open_adj/high_adj/low_adj/close_adj/vwap_adj` are present, the checker checks nulls and verifies adjusted prices approximately equal raw prices multiplied by `adj_factor`.

Raw TuShare cache:

- Whether `manifest.sqlite` exists.
- Date range for each API, partition count, and total row count.
- Number of schema hashes and content hashes.
- Missing or empty source partitions: an error is reported when `daily` has rows for a trading date but that date has no `adj_factor` or `daily_basic` rows.
- Multiple schema-hash versions are reported as warnings to help identify upstream TuShare field changes.

Factor store:

- Whether `manifest.json` exists; base-panel row and column counts; and schema hash.
- Factor families, prefixes, columns, rows, and partition counts.
- Whether base and factor files referenced by the manifest exist.
- Alignment status in `key_validation`.
- Factor-value checks stream through parquet partitions instead of loading the entire store into pandas. Checks include actual row and column counts, partition row-count metadata, duplicate `date, ticker` keys, NaN and Inf counts, maximum null rate, all-null columns, and constant columns.
- Text output names all-null, constant, and high-null-rate columns. `--factor-family` limits the scan to selected families, `--skip-factor-quality` checks only manifest metadata and file existence, and `--progress` reports partition scan progress to stderr.

Backtest artifacts:

- Presence of `experiment_manifest.json`, metrics, run configuration, and common parquet outputs.
- Total artifact-directory size.

## Refresh strategy

Use the raw cache for incremental refreshes and to rebuild the base panel:

```bash
uv run moneytrees-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/panel/cn/cn_daily_raw.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --benchmark 000300.SH \
  --sanity-check warn
```

After the base panel is stable, generate local and external factors as needed:

```bash
uv run moneytrees-factor-store \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output-dir data/factor_store/cn \
  --factor-family alpha158 \
  --factor-family alpha360 \
  --factor-dtype float32 \
  --chunk-trade-dates 60
```

The DolphinDB external producer computes Alpha101/191 and writes them to the same factor store:

```bash
uv run moneytrees-dolphindb-alphas \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn \
  --no-wide-output \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --alpha101 \
  --alpha191 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --stream-input auto
```

For parquet input with `--no-wide-output`, the external Alpha CLI defaults to `--stream-input auto`, reading input, uploading it to DolphinDB, downloading results, and writing output in chunks. Retain historical context using `--dolphindb-warmup-trade-dates` so rolling, delay, rank, and correlation operators do not suffer from window-boundary contamination. Wide output or `--stream-input off` still uploads the full input; validate with a small sample first when memory is constrained.

## Storage estimates

For five years, about 1,200 trading days, and roughly 5,000 stocks, one factor matrix has about six million rows:

```text
6000000 * 810 * 8 bytes ~= 38.9 GB  # float64 raw values
6000000 * 810 * 4 bytes ~= 19.4 GB  # float32 raw values
```

Parquet compression reduces on-disk size, but raw cache, base panels, factor stores, and backtest artifacts accumulate. Plan for tens to hundreds of GB for multi-year, full-market experiments with all 810 factors.

## Parquet policy

Money Trees defaults to `zstd` compression at level 3 for new parquet output. To retain compatibility with older output, pass:

```bash
--compression snappy
```

Set a row-group size explicitly when needed:

```bash
--row-group-size 100000
```

Recommendations:

- Raw cache: use parquet partitions; new writes default to `zstd` level 3 when storage is constrained.
- Base panels: default to `zstd` level 3.
- Factor stores: default to `float32` and `zstd` level 3.
- Backtest artifacts: default to `zstd`; avoid exporting a full preprocessed parquet by default.
- Do not use pickle as a long-term data format. Reserve CSV for small reports.

Existing files are not migrated automatically. Rewrite to a separate output path:

```bash
uv run moneytrees-parquet-rewrite \
  --input data/cn_daily_raw.parquet \
  --output data/panel/cn/cn_daily_raw.parquet \
  --compression zstd \
  --compression-level 3 \
  --row-group-size 100000
```

## Preview before cleanup

There is currently no automatic cleanup command. Inspect storage read-only before removing files:

```bash
du -sh data/raw/tushare data/panel data/factor_store artifacts 2>/dev/null
```

List the largest files:

```bash
find data artifacts -type f -name "*.parquet" -printf "%s %p\n" 2>/dev/null \
  | sort -nr \
  | head -20
```

Any future cleanup tool must default to preview: list candidate files, sizes, and reasons, and require explicit confirmation before deletion. Never silently clean `data/`, `artifacts/`, the raw TuShare cache, or a factor store.
