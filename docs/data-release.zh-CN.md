# 数据发布资产

[English page](https://runchengxie.github.io/money-trees/data-release/)

`moneytrees-data-release` 用来生成适合上传到 GitHub Releases 的数据发布资产。它会复制基础面板，把原始缓存和因子仓库（factor store）整理成不压缩的 tar 分片，并写出元数据清单、校验码和 README。

基础用法：

```bash
uv run moneytrees-data-release \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn_daily \
  --output-dir data/releases/cn_daily_raw \
  --label cn_daily_raw
```

WSL 环境中可以直接把目标放到 Windows 盘，减少 WSL 文件系统空间占用：

```bash
uv run moneytrees-data-release \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --factor-store data/factor_store/cn_daily \
  --output-dir /mnt/d/money-tree-releases/cn_daily_raw
```

`--output-dir` 也接受 `D:/money-tree-releases/cn_daily_raw` 形式，会转换到 `/mnt/d/...`。命令默认会在写入前检查目标文件系统剩余空间。只有在外部监控空间或已确认可写容量时，才使用 `--skip-space-check`。

输出目录包含：

```text
manifest.json
sha256sums.txt
README.md
panel__cn_daily_raw.parquet
raw_cache_part001.tar
factor_store_part001.tar
```

生成规则：

- 单个资产默认控制在 1536 MiB 以下，满足 GitHub Releases 单文件小于 2 GiB 的约束。
- 基础面板文件小于阈值时直接复制，超过阈值时拆成 `.partNNNofMMM`。
- 原始缓存目录和因子仓库目录默认写成不压缩 tar 分片，避免对 parquet 进行低收益的二次压缩。
- 命令默认支持可恢复输出复用：重跑同一命令时，已完整生成且校验通过的资产会跳过。半截或校验失败的生成资产会重写。
- `manifest.json` 记录输入路径、基础面板摘要、资产列表、每个资产的 SHA-256、分片策略和 git commit 信息。
- `sha256sums.txt` 用于下载后执行 `sha256sum -c sha256sums.txt`。

只预览：

```bash
uv run moneytrees-data-release \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --factor-store data/factor_store/cn_daily \
  --output-dir data/releases/cn_daily_raw \
  --dry-run
```

实际生成时可以加 `--progress`，把当前资产和总体进度输出到 stderr。确实需要严格禁止复用已有生成文件时，可以加 `--no-resume`。需要强制重写所有生成资产时，使用 `--overwrite`。

上传前建议先检查授权边界。TuShare 原始数据和由它派生的因子是否可以公开发布，取决于数据源协议和你的账号授权。未确认前优先使用私有仓库或对象存储。

使用 GitHub CLI 上传到已有 release：

```bash
uv run moneytrees-data-release \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --factor-store data/factor_store/cn_daily \
  --output-dir data/releases/cn_daily_raw \
  --github-repo OWNER/REPO \
  --github-tag data-cn-2026-05-03 \
  --upload
```

如果 release 还不存在，可以加 `--create-release`：

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

恢复时先校验，再按 README 提示解 tar 和拼接 `.part*` 文件。拆分文件是字节级备份分片，拼回原文件后再用 parquet 工具读取。
