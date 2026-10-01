# 数据快照

[English page](data-snapshot.md)

`moneytrees-data-snapshot` 用来记录 Money Trees 标准面板的数据版本信息。它只写入 metadata、checksum 和 README，不复制大型 parquet、原始缓存或因子仓库文件。

基础用法：

```bash
uv run moneytrees-data-snapshot \
  --panel data/panel/cn/cn_daily_2016_2025.parquet \
  --raw-cache data/raw/tushare \
  --output-dir data/snapshots/cn_daily_2016_2025 \
  --label cn_daily_2016_2025
```

输出目录包含：

```text
dataset_meta.json
checksums.sha256
README.md
```

`dataset_meta.json` 记录面板路径、文件大小、SHA-256、行数、列数、日期范围、ticker 数量、parquet 表结构哈希、可选原始缓存/因子仓库引用、轻量质量摘要和可用的 git commit 信息。

质量摘要包含：

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

质量摘要用于回答备份前的数据是否已经通过 `moneytrees-data-status` 暴露的轻量检查。它不会修复数据，也不会嵌入大体量的逐日期或逐 ticker 诊断。

同时记录因子仓库和说明：

```bash
uv run moneytrees-data-snapshot \
  --panel data/panel/cn/cn_daily_2016_2025.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn_daily \
  --output-dir data/snapshots/cn_daily_2016_2025_full \
  --label cn_daily_2016_2025_full \
  --note "full 810 factor research snapshot"
```

这个命令用于保存数据版本记录。大型文件本身请用 `cp`、`rsync` 或对象存储工具复制。
