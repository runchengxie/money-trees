# Data Snapshot

`moneytrees-data-snapshot` records a lightweight, reproducible metadata snapshot for a Money Trees panel. It writes metadata and checksum files only; it does not copy large parquet, raw cache, or factor store files.

Use it after generating a canonical panel:

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

`dataset_meta.json` includes the panel path, file size, SHA-256, row count, column count, date range, ticker count, parquet schema hash, optional raw cache/factor store references, and git commit metadata when available.

Use `--factor-store` when you also want the snapshot to record a factor store manifest:

```bash
uv run moneytrees-data-snapshot \
  --panel data/panel/cn/cn_daily_2016_2025.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn_daily \
  --output-dir data/snapshots/cn_daily_2016_2025_full \
  --label cn_daily_2016_2025_full
```

The command is intended for dataset version records. Use system tools such as `cp`, `rsync`, or remote object storage tools to copy the large files themselves.
