# Data release assets

[Chinese version](https://runchengxie.github.io/money-trees/zh-CN/data-release/)

`moneytrees-data-release` creates data assets suitable for GitHub Releases. It copies the base panel, packages the raw cache and factor store into tar shards, and writes a manifest, checksums, and a README. Raw-cache shards can optionally use Zstandard compression; factor-store shards remain uncompressed because their Parquet files are already compressed.

```bash
uv run moneytrees-data-release \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn_daily \
  --raw-cache-compression zstd \
  --output-dir data/releases/cn_daily_raw \
  --label cn_daily_raw
```

Install the optional compression dependency before enabling this option:

```bash
uv sync --extra release
```

Compression levels range from 1 to 22. The default is 19, with a 27-bit long-distance window to match the SimFin archive approach; use a lower level when generation time matters more than archive size. The `none` mode remains available and is the CLI default for compatibility.

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
raw_cache_zstd19_part001.tar.zst
factor_store_part001.tar
```

Generation rules:

- Each asset defaults to a maximum size below 1536 MiB, within GitHub Releases' per-file limit of less than 2 GiB.
- A base panel below the limit is copied directly; a larger panel is split into `.partNNNofMMM` pieces.
- Raw-cache tar shards use Zstandard only when `--raw-cache-compression zstd` is selected. The manifest records the codec and level for each asset.
- Factor-store tar shards remain uncompressed; their Parquet files already use Zstandard compression, and higher levels saved little in the measured sample.
- Zstandard shard planning keeps headroom below the asset-size limit and checks each compressed asset's actual size.
- Output reuse is resumable by default. A rerun skips complete generated assets that pass validation and rewrites partial or invalid generated assets.
- `manifest.json` records input paths, the base-panel summary, asset list, each asset's SHA-256, shard policy, and available Git commit information.
- After download, verify assets with `sha256sum -c sha256sums.txt`. Extract Zstandard shards with `zstd -d -c <asset>.tar.zst | tar -xf -`; extract ordinary tar shards with `tar -xf <asset>.tar`.

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

To restore an asset, verify it first, then extract `.tar.zst` shards with `zstd -d -c <asset>.tar.zst | tar -xf -` and uncompressed tar shards with `tar -xf <asset>.tar`. Reassemble any `.part*` files in order as described in the generated README. Split files are byte-level backup shards; reassemble them before opening the original file with parquet tools.
