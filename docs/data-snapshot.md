# Data snapshots

[简体中文](data-snapshot.zh-CN.md)

`moneytrees-data-snapshot` records version metadata for a Money Trees standard panel. It writes metadata, checksums, and a README. It does not copy large parquet files, raw caches, or factor-store files.

```bash
uv run moneytrees-data-snapshot \
  --panel data/panel/cn/cn_daily_2016_2025.parquet \
  --raw-cache data/raw/tushare \
  --output-dir data/snapshots/cn_daily_2016_2025 \
  --label cn_daily_2016_2025
```

The output directory contains:

```text
dataset_meta.json
checksums.sha256
README.md
```

`dataset_meta.json` records the panel path, file size, SHA-256, row and column counts, date range, ticker count, parquet schema hash, optional raw-cache and factor-store references, a lightweight quality summary, and available Git commit information.

The quality summary contains:

```text
status
checked_at_utc
duplicate_key_count
missing_required_columns
null_counts
derived_return_checks
adjusted_price_checks
raw_cache_anomalies
errors
warnings
```

The summary indicates whether the data passed the lightweight checks exposed by `moneytrees-data-status` before backup. It does not repair data or include large per-date or per-ticker diagnostics.

To include a factor-store reference and a note:

```bash
uv run moneytrees-data-snapshot \
  --panel data/panel/cn/cn_daily_2016_2025.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn_daily \
  --output-dir data/snapshots/cn_daily_2016_2025_full \
  --label cn_daily_2016_2025_full \
  --note "full 810 factor research snapshot"
```

This command saves a data-version record. Copy large files separately with `cp`, `rsync`, or an object-storage tool.
