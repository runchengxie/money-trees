# 数据状态检查

本文说明 Money Trees 的数据分层、状态检查命令和存储策略。README 只保留入口链接；日常排障、覆盖确认和空间估算放在这里。

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

检查基础面板：

```bash
uv run moneytrees-data-status \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --format text \
  --mode warn
```

检查 TuShare raw cache：

```bash
uv run moneytrees-data-status \
  --raw-cache data/raw/tushare \
  --format text
```

检查 factor store：

```bash
uv run moneytrees-data-status \
  --factor-store data/factor_store/cn/manifest.json \
  --format text
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
  --panel data/panel/cn/cn_daily_raw.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn/manifest.json \
  --artifacts artifacts/xgb-alpha-all \
  --format json \
  --mode error
```

`--mode warn` 会报告问题但不因数据错误返回失败；`--mode error` 遇到错误会返回非零退出码。参数错误和无法读取输入仍会失败。

## 检查项

基础面板检查：

- 文件大小、行数、列数。
- 日期范围、交易日数量、ticker 数量。
- 重复 `date, ticker` 键。
- 必需列缺失。
- 关键列缺失率。
- 非正价格、负成交量、`high < low`。

TuShare raw cache 检查：

- `manifest.sqlite` 是否存在。
- 每个 API 的日期范围。
- 分片数量和累计行数。
- schema hash 和 content hash 数量。

factor store 检查：

- `manifest.json` 是否存在。
- base panel 行数、列数、schema hash。
- 因子族、前缀、列数、行数、分片数量。
- manifest 指向的 base/factor 文件是否存在。
- `key_validation` 中的对齐状态。

artifacts 检查：

- `experiment_manifest.json`、metrics、run config 和常见 parquet 输出是否存在。
- 产物目录总大小。

## 刷新策略

raw cache 适合增量刷新和重建基础面板：

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

Alpha101/191 由 DolphinDB 外部生产器全量计算后写入同一个 factor store：

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
  --chunk-trade-dates 60
```

第一版不会把 Alpha101/191 在 DolphinDB 侧按 chunk 计算；这是为了避免滚动窗口、delay、rank 和 correlation 类算子的边界污染。Python 侧只负责把已验证的全量结果按日期 chunk 落盘。

## 空间估算

以 5 年约 1200 个交易日、全市场约 5000 只股票估算，单个因子矩阵约 600 万行：

```text
6000000 * 810 * 8 bytes ~= 38.9 GB  # float64 裸数据
6000000 * 810 * 4 bytes ~= 19.4 GB  # float32 裸数据
```

Parquet 压缩会降低落盘体积，但 raw cache、基础面板、factor store 和 artifacts 会叠加占用。完整 810 因子多年全市场实验应按几十 GB 到上百 GB 规划。

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

- raw cache：默认 parquet 分片；空间紧张时新写入使用默认 `zstd` level 3。
- 基础面板：默认 `zstd` level 3。
- factor store：默认 `float32` + `zstd` level 3。
- artifacts：默认 `zstd`，避免默认导出完整预处理 parquet。
- pickle 不作为长期数据格式；CSV 只用于小报表。

已有文件不会自动迁移。需要重写时使用旁路输出：

```bash
uv run moneytrees-parquet-rewrite \
  --input data/cn_daily_raw.parquet \
  --output data/panel/cn/cn_daily_raw.parquet \
  --compression zstd \
  --compression-level 3 \
  --row-group-size 100000
```

## 清理前 dry-run

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

后续如果增加清理工具，默认必须 dry-run：先打印候选文件、大小和原因，只有显式确认后才允许删除。不要对 `data/`、`artifacts/`、raw TuShare cache 或 factor store 做隐式清理。
