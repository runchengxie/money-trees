# 数据状态检查

本文说明 Money Trees 的数据分层、状态检查命令和存储策略。README 只保留入口链接。日常排障、覆盖确认和空间估算放在这里。

## 数据分层

推荐把运行数据分成四层：

```text
data/raw/tushare/        TuShare 原始接口缓存，可重建基础面板
data/panel/cn/           清洗后的基础 date,ticker 面板，不内嵌大批因子
data/factor_store/cn/    Alpha101/191/158/360 分族、分日期 chunk 的因子存储
artifacts/               回测输出，按实验保留或短生命周期清理
```

`date, ticker` 是标准面板键。市场配置档（market profile）仍由 `configs/market/cn.yaml` 和 `src/moneytree/markets/cn.py` 管理，默认基准是 `000300.SH`。

## 查看当前覆盖

`moneytrees-data-status` 是只读命令，不删除、不刷新、不修复、不重写文件。

检查基础面板。Parquet 面板会走 streaming / narrow-column 检查路径，避免为了状态检查把多年全市场面板完整读进 pandas：

```bash
uv run moneytrees-data-status \
  --panel data/panel/cn/cn_daily_2016_2025.parquet \
  --format text \
  --mode warn
```

检查 TuShare 原始缓存：

```bash
uv run moneytrees-data-status \
  --raw-cache data/raw/tushare \
  --format text
```

检查因子仓库：

```bash
uv run moneytrees-data-status \
  --factor-store data/factor_store/cn/manifest.json \
  --format text
```

全量因子仓库质量检查会逐分片扫描所有因子值。需要快速确认元数据时先跳过值扫描。需要定位单个因子族时只扫对应因子族：

```bash
uv run moneytrees-data-status \
  --factor-store data/factor_store/cn/manifest.json \
  --skip-factor-quality

uv run moneytrees-data-status \
  --factor-store data/factor_store/cn/manifest.json \
  --factor-family alpha191 \
  --progress
```

对已知不可用或定义上恒定的列，可用 `--allow-factor-column` 标记为允许，从而把状态检查聚焦到新的异常。例如 Alpha191 的 `alpha191_030` 依赖外部 `MKT/SMB/HML` 输入。Alpha360 的 lag0 相对变化列按定义为 0：

```bash
uv run moneytrees-data-status \
  --factor-store data/factor_store/cn/manifest.json \
  --allow-factor-column alpha191_030 \
  --allow-factor-column alpha360_close_lag00,alpha360_volume_lag00 \
  --mode error
```

检查回测产物：

```bash
uv run moneytrees-data-status \
  --artifacts artifacts/xgb-alpha-all \
  --format text
```

一次性检查四层，并在 CI 中用 JSON：

```bash
uv run moneytrees-data-status \
  --panel data/panel/cn/cn_daily_2016_2025.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn/manifest.json \
  --artifacts artifacts/xgb-alpha-all \
  --format json \
  --mode error
```

`--mode warn` 会报告问题但不因数据错误返回失败。`--mode error` 遇到错误会返回非零退出码。参数错误和无法读取输入仍会失败。`moneytrees-data-status` 仍然是只读命令：它不会刷新原始缓存、不会修复面板，也不会重写因子仓库或回测产物。

## 检查项

基础面板检查：

- 文件大小、行数、列数。
- 日期范围、交易日数量、ticker 数量。
- 重复 `date, ticker` 键。
- 必需列缺失。
- 关键列缺失数量和缺失率。
- 原始和复权价格的非正值、负成交量、`high < low`。
- parquet 面板按 streaming / narrow-column 方式扫描。如果 `date, ticker` 不是排序状态，会报告乱序并使用窄列 fallback 计算精确重复键数量。
- 派生收益列一致性：`return_1d`、`next_period_return`、`benchmark_return`、`benchmark_next_period_return` 会按 `close_adj`（缺失时用 `close`）和 `benchmark_close` 重新计算后比对。
- 允许自然边界空值：每个 ticker 第一条 `return_1d`、每个 ticker 最后一条 `next_period_return`、全局首日 `benchmark_return`、全局末日 `benchmark_next_period_return`。
- 复权列一致性：当存在 `adj_factor` 和 `open_adj/high_adj/low_adj/close_adj/vwap_adj` 时，检查空值，并验证复权列约等于原始价格乘以 `adj_factor`。

TuShare 原始缓存检查：

- `manifest.sqlite` 是否存在。
- 每个 API 的日期范围。
- 分片数量和累计行数。
- schema hash 和 content hash 数量。
- 原始缓存异常分片：当 `daily` 某交易日有行数，但同日 `adj_factor` 或 `daily_basic` 为 0 行或缺失时报告错误。
- schema hash 多版本会作为 warning 展示，便于识别 TuShare 上游字段变化。

因子仓库检查：

- `manifest.json` 是否存在。
- 基础面板行数、列数、schema hash。
- 因子族、前缀、列数、行数、分片数量。
- 元数据清单指向的 base/factor 文件是否存在。
- `key_validation` 中的对齐状态。
- 因子值卫生检查会按 parquet 分片 streaming 扫描，不把完整因子仓库一次性读进 pandas。检查项包括实际行数/列数、分片行数元数据、重复 `date, ticker`、NaN 数量、Inf 数量、最大空值率、整列全空和整列常数。
- 文本输出会列出整列全空、整列常数和高空值率列名。`--factor-family` 可只检查指定因子族，`--skip-factor-quality` 可只检查元数据清单和文件存在性，`--progress` 可把分片扫描进度输出到 stderr。

回测产物检查：

- `experiment_manifest.json`、metrics、run config 和常见 parquet 输出是否存在。
- 产物目录总大小。

## 刷新策略

原始缓存适合增量刷新和重建基础面板：

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

基础面板稳定后，再按需生成本地和外部因子：

```bash
uv run moneytrees-factor-store \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output-dir data/factor_store/cn \
  --factor-family alpha158 \
  --factor-family alpha360 \
  --factor-dtype float32 \
  --chunk-trade-dates 60
```

Alpha101/191 由 DolphinDB 外部生产器全量计算后写入同一个因子仓库：

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

parquet 输入配合 `--no-wide-output` 时，外部 Alpha CLI 默认按 `--stream-input auto` 分片读取输入、上传到 DolphinDB、下载结果并落盘。每个窗口应保留 `--dolphindb-warmup-trade-dates` 历史上下文，避免滚动窗口、delay、rank 和 correlation 类算子的边界污染。宽表输出或 `--stream-input off` 仍会走完整输入上传路径，内存紧张时先用小样本验证。

## 空间估算

以 5 年约 1200 个交易日、全市场约 5000 只股票估算，单个因子矩阵约 600 万行：

```text
6000000 * 810 * 8 bytes ~= 38.9 GB  # float64 裸数据
6000000 * 810 * 4 bytes ~= 19.4 GB  # float32 裸数据
```

Parquet 压缩会降低落盘体积，但原始缓存、基础面板、因子仓库和回测产物会叠加占用。完整 810 因子多年全市场实验应按几十 GB 到上百 GB 规划。

## Parquet 策略

Money Trees 新写入 parquet 默认使用 `zstd`，默认 level 3。需要兼容旧输出时显式传：

```bash
--compression snappy
```

需要控制 row group 时显式传：

```bash
--row-group-size 100000
```

建议：

- 原始缓存：默认 parquet 分片。空间紧张时新写入使用默认 `zstd` level 3。
- 基础面板：默认 `zstd` level 3。
- 因子仓库：默认 `float32` + `zstd` level 3。
- 回测产物：默认 `zstd`，避免默认导出完整预处理 parquet。
- pickle 不作为长期数据格式。CSV 只用于小报表。

已有文件不会自动迁移。需要重写时使用旁路输出：

```bash
uv run moneytrees-parquet-rewrite \
  --input data/cn_daily_raw.parquet \
  --output data/panel/cn/cn_daily_raw.parquet \
  --compression zstd \
  --compression-level 3 \
  --row-group-size 100000
```

## 清理前只预览

当前没有自动清理命令。清理前先只读检查空间：

```bash
du -sh data/raw/tushare data/panel data/factor_store artifacts 2>/dev/null
```

查看大文件：

```bash
find data artifacts -type f -name "*.parquet" -printf "%s %p\n" 2>/dev/null \
  | sort -nr \
  | head -20
```

后续如果增加清理工具，默认必须只预览：先打印候选文件、大小和原因，只有显式确认后才允许删除。不要对 `data/`、`artifacts/`、TuShare 原始缓存或因子仓库做隐式清理。
