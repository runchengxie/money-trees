# Data release assets

[简体中文](https://runchengxie.github.io/money-trees/zh-CN/data-release/)

`moneytrees-data-release` creates data assets suitable for GitHub Releases. It copies the base panel, packages raw-cache and factor-store directories into uncompressed tar shards, and writes a manifest, checksums, and a README.

```bash
uv run moneytrees-data-release \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn_daily \
  --output-dir data/releases/cn_daily_raw \
  --label cn_daily_raw
```

In WSL, the output can be placed directly on a Windows drive to reduce space used on the WSL filesystem:

```bash
uv run moneytrees-data-release \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --factor-store data/factor_store/cn_daily \
  --output-dir /mnt/d/money-tree-releases/cn_daily_raw
```

`--output-dir` also accepts a path such as `D:/money-tree-releases/cn_daily_raw`, which is converted to `/mnt/d/...`. Before writing, the command checks available space on the target filesystem. Use `--skip-space-check` only when external monitoring or a verified capacity check confirms sufficient space.

The output directory contains files such as:

```text
manifest.json
sha256sums.txt
README.md
panel__cn_daily_raw.parquet
raw_cache_part001.tar
factor_store_part001.tar
```

Generation rules:

- Each asset defaults to a maximum size below 1536 MiB, within GitHub Releases' per-file limit of less than 2 GiB.
- A base panel below the limit is copied directly; a larger panel is split into `.partNNNofMMM` pieces.
- Raw-cache and factor-store directories are written as uncompressed tar shards by default, avoiding a second, low-benefit compression pass over parquet files.
- Output reuse is resumable by default. A rerun skips complete generated assets that pass validation and rewrites partial or invalid generated assets.
- `manifest.json` records input paths, the base-panel summary, asset list, each asset's SHA-256, shard policy, and available Git commit information.
- After download, verify assets with `sha256sum -c sha256sums.txt`.

Preview without writing assets:

```bash
uv run moneytrees-data-release \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --factor-store data/factor_store/cn_daily \
  --output-dir data/releases/cn_daily_raw \
  --dry-run
```

Add `--progress` to report the current asset and overall progress to stderr. Use `--no-resume` to prohibit reuse of existing generated files, or `--overwrite` to force regeneration of all generated assets.

Before uploading, verify the data-sharing authorization. Whether raw TuShare data and derived factors may be published depends on the source agreement and account permissions. Until confirmed, prefer a private repository or object storage.

Upload to an existing GitHub Release:

```bash
uv run moneytrees-data-release \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --factor-store data/factor_store/cn_daily \
  --output-dir data/releases/cn_daily_raw \
  --github-repo OWNER/REPO \
  --github-tag data-cn-2026-05-03 \
  --upload
```

Add `--create-release` if the release does not exist:

```bash
uv run moneytrees-data-release \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --factor-store data/factor_store/cn_daily \
  --output-dir data/releases/cn_daily_raw \
  --github-repo OWNER/REPO \
  --github-tag data-cn-2026-05-03 \
  --create-release \
  --upload
```

To restore an asset, verify it first, then extract tar files and reassemble any `.part*` files as described in the generated README. Split files are byte-level backup shards; reassemble them before opening the original file with parquet tools.
