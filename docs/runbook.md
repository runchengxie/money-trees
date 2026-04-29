# Runbook

Runbook 记录日常执行、排障和归档检查。常见使用示例见 [cookbook.md](cookbook.md)。

## 运行模式

### 模式 A：最小回测

只需要已有标准 `date, ticker` 面板，不需要 TuShare、XGBoost、DolphinDB 或 Optuna。

### 模式 B：本地 518 因子

使用 TuShare 拉取日频数据，并追加本地 Alpha158/360。

### 模式 C：完整 810 因子

在模式 B 的基础上，用 DolphinDB 离线生成 Alpha101/191，写入同一个 factor store 后再回测。

## 日常运行顺序

1. 更新依赖。

```bash
uv sync --dev --extra research
```

2. 刷新 TuShare raw cache 并生成基础 `date, ticker` 面板。

```bash
uv run moneytrees-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/panel/cn/cn_daily_raw.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --progress \
  --benchmark 000300.SH \
  --sanity-check warn
```

3. 按需生成本地 Alpha158/360 factor store。

```bash
uv run moneytrees-factor-store \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output-dir data/factor_store/cn_daily \
  --factor-family alpha158 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --progress
```

需要 Alpha360 时可再次运行同一输出目录，只追加缺失的因子族：

```bash
uv run moneytrees-factor-store \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output-dir data/factor_store/cn_daily \
  --factor-family alpha360 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --progress
```

`moneytrees-factor-store` 会按分区复用已生成的本地因子文件。重复运行同一 family 时，已完成且输入一致的 partition 会跳过；基础面板扩展到新日期后，只补缺失或输入变化的 partition。需要强制全量重算时传 `--overwrite`。`--progress` 会输出 ASCII 进度条、每个 partition 的 `generated/skipped` 状态、单块耗时、累计耗时和 ETA。

回测入口可以直接读取 factor store manifest，并按配置只加载需要的因子族：

```bash
uv run moneytrees \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/alpha158-only \
  --set 'features.include_factor_families=["alpha158"]'
```

4. 检查数据状态。

```bash
uv run moneytrees-data-status \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn_daily/manifest.json \
  --format text \
  --mode warn
```

5. 可选：离线生成外部 Alpha101/191。

Alpha101/191 需要先由 DolphinDB 等外部生产器生成后写入 factor store。详细 WSL/Docker 和 DolphinDB 模块说明见 [dolphindb_alpha101_191.md](dolphindb_alpha101_191.md)。

```bash
uv sync --dev --extra external-alphas

uv run moneytrees-dolphindb-alphas \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn_daily \
  --no-wide-output \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --alpha101 \
  --alpha191 \
  --factor-dtype float32 \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

生成后检查：

```bash
test -f data/factor_store/cn_daily/manifest.json
uv run moneytrees-data-status \
  --factor-store data/factor_store/cn_daily/manifest.json \
  --mode error
```

6. 跑主回测。

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/xgb-alpha-all
```

7. 检查输出。

```bash
test -f artifacts/xgb-alpha-all/metrics.json
test -f artifacts/xgb-alpha-all/run_config.json
test -f artifacts/xgb-alpha-all/run_summary.txt
```

8. 跑测试和 lint。

```bash
uv run pytest -q
uv run ruff check .
```

## 完整 810 因子运行前检查

- 标准面板包含 `date, ticker`。
- Alpha191 所需的 `benchmark_open` 和 `benchmark_close` 存在。
- Alpha101 所需的 `circ_mv` 或 `total_mv`、`industry` 字段已准备。
- 行业字段最好是 point-in-time 口径，避免历史回测未来信息污染。
- DolphinDB wrapper 函数版本已记录。
- `wq101alpha`、`gtja191Alpha` 和 `moneytreeAlpha` 模块版本已记录。
- factor store manifest 已保存并归档。
- 回测输入优先使用 `data/factor_store/cn_daily/manifest.json`。

## 存储压力与因子数据管理

完整 Alpha101、Alpha191、Alpha158 和 Alpha360 合计 810 个因子列。以 5 年约 1200 个交易日、全市场约 5000 只股票估算，单个因子矩阵约有 600 万行：

```text
6000000 * 810 * 8 bytes  ~= 38.9 GB  # float64 裸数据
6000000 * 810 * 4 bytes  ~= 19.4 GB  # float32 裸数据
```

Parquet 压缩通常能降低落盘体积，但真实占用还会叠加 raw cache、基础行情列、`daily_basic`、可交易过滤、基准列、factor store 分片、兼容宽表输出、`export_parquet` 和多次实验产物。完整 810 因子全市场多年运行应按几十 GB 到上百 GB 的本地空间规划。

当前默认策略：

- TuShare 本地 Alpha158/360 和 DolphinDB 外部 Alpha101/191 生成路径默认把 `alpha101_`、`alpha191_`、`alpha158_`、`alpha360_` 因子列保存为 `float32`。
- 新写入的 Money Trees parquet 输出默认使用 `zstd` 压缩，默认压缩级别为 3；需要兼容旧行为时显式传 `--compression snappy`。
- 推荐先用 `moneytrees-tushare` 生成基础面板，再用 `moneytrees-factor-store` 按需生成 `alpha158` 或 `alpha360` 分族因子文件。
- 需要精度敏感复核时，生成命令显式传 `--factor-dtype float64`。
- 回测可用 `features.include_factor_prefixes` 或 `features.include_factor_families` 只读取需要的因子族；parquet 输入会尽量做列裁剪。
- `output.export_parquet` 会额外保存预处理后的面板，只建议用于调试和复现实验。

建议把数据分成四层理解：

```text
data/raw/tushare/       TuShare 原始接口缓存，可重建标准面板
data/panel/             清洗后的基础 date,ticker 面板
data/factor_store/      Alpha101/191/158/360 分族因子文件
artifacts/              回测指标、信号、持仓、配置和 manifest
```

raw cache、基础面板、factor store 和 experiment artifacts 的保留周期不同。不要自动删除这些目录；清理前先 dry-run 检查体积和文件列表。

### 存储检查 dry-run

以下命令只读取目录大小，不删除文件：

```bash
du -sh data/raw/tushare data/panel data/factor_store artifacts 2>/dev/null
```

查看较大的 parquet 文件：

```bash
find data artifacts -type f -name "*.parquet" -printf "%s %p\n" 2>/dev/null \
  | sort -nr \
  | head -20
```

如果后续增加 `gc` 或清理命令，默认必须是 dry-run：先打印候选文件、大小和原因，只有显式传入非 dry-run 参数后才允许删除。不要对 `data/`、`artifacts/`、raw TuShare cache 或 factor store 做隐式清理。

### Parquet 压缩迁移

现有面板可以旁路重写为 zstd，不覆盖原文件：

```bash
uv run moneytrees-parquet-rewrite \
  --input data/cn_daily_raw.parquet \
  --output data/panel/cn/cn_daily_raw.parquet \
  --compression zstd
```

该命令会拒绝原地重写，并在写入后默认校验行数、列和索引名称。确认新文件可用后，再手工更新后续命令中的 `--data` 或 `--input` 路径。

## TuShare token 排查

Token 读取顺序：

1. `--token`
2. `TUSHARE_TOKEN`
3. `TUSHARE_PRO_TOKEN`
4. `TS_TOKEN`
5. `TUSHARE_API_KEY`
6. `.env` 文件中的同名变量

缺 token 时会报：

```text
Missing TuShare token.
```

处理方式：

- 确认 `.env` 存在且没有提交到 git。
- 确认变量名在支持列表内。
- 用 `--token` 临时覆盖。

## Raw cache 检查

raw cache 默认结构：

```text
data/raw/tushare/
  manifest.sqlite
  daily/trade_date=YYYYMMDD.parquet
  daily_basic/trade_date=YYYYMMDD.parquet
  adj_factor/trade_date=YYYYMMDD.parquet
  stk_limit/trade_date=YYYYMMDD.parquet
  suspend_d/trade_date=YYYYMMDD.parquet
```

检查 manifest：

```bash
sqlite3 data/raw/tushare/manifest.sqlite \
  "select api_name, count(*) from raw_cache group by api_name;"
```

近期数据回填时使用：

```bash
uv run moneytrees-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --progress
```

接口字段口径变化或 cache 明显损坏时，可以对特定 API 或日期做定向清理后重拉。清理前先确认没有其他实验依赖同一缓存目录。

## TuShare 长任务性能与排障

长区间全市场拉取会按交易日调用多个 TuShare 接口。`daily`、`daily_basic`、`adj_factor`、`stk_limit` 和 `suspend_d` 都可能循环覆盖全部交易日；5 年全 A 股日频面板通常会产生数百万行，首次运行较慢是正常情况。本地 Alpha158/360 还会在标准面板上追加滚动、滞后和截面特征，写 parquet 前也需要额外时间。

建议：

- 正式拉取始终设置 `--cache-dir data/raw/tushare`。
- 重复运行时搭配 `--refresh-recent-days 20` 刷新近期交易日。
- 长任务加 `--progress`；需要更频繁输出时使用 `--progress-every 10`。
- CLI 默认以 `--request-interval-seconds 0.13` 控制真实 TuShare 请求间隔，并在频率超限时按 `--rate-limit-wait-seconds` 等待后重试；cache 命中不会等待。
- 调试时先限制日期范围和股票池，例如 `--tickers 000001.SZ,600000.SH`。
- 只定位 TuShare/API 连通性时，先不加 `--factor-family`。
- 只定位基础接口时，可临时使用 `--skip-daily-basic`、`--skip-adj-factor`、`--skip-limits`、`--skip-suspend` 和 `--skip-stock-basic`，但正式回测通常需要这些列支撑可交易过滤。
- `--raw-features` 只改变本地 Alpha158/360 使用复权价格还是未复权价格，不会减少拉取量，也不是快速模式。

小范围调试示例：

```bash
uv run moneytrees-tushare \
  --start-date 20241201 \
  --end-date 20241231 \
  --tickers 000001.SZ,600000.SH \
  --output data/debug_alpha_raw.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --progress \
  --factor-family alpha158 \
  --raw-features
```

## 常见失败

### 缺基准收益列

报错通常包含：

```text
benchmark_next_period_return
```

处理：

- 检查输入文件是否包含该列。
- 如果上游列名不同，在 `configs/market/cn.yaml` 里设置 `benchmark_return_column`。

### 缺基准累计列

报错通常包含：

```text
benchmark_cum_ret
```

处理：

- 检查输入文件是否包含基准累计收益。
- 如果上游列名不同，在 `configs/market/cn.yaml` 里设置 `benchmark_cum_column`。

### 可交易过滤列缺失

报错通常包含：

```text
tradability column mapping
```

处理：

- 补齐 `is_suspended`、`is_st`、`hit_up_limit`、`hit_down_limit`。
- 临时关闭对应过滤，例如 `--set market.tradability_filters.st=false`。

### 训练或验证样本为空

报错通常包含：

```text
empty train/valid frame
```

处理：

- 检查数据时间范围是否覆盖 segment 固定训练和验证区间。
- 检查可交易过滤是否过滤掉全部样本。
- 检查 `feature_lag_periods` 后是否仍有样本。
- smoke 调试时先减少窗口数量。

### XGBoost 依赖缺失

报错通常包含：

```text
optional xgboost dependency
```

处理：

```bash
uv sync --dev --extra xgboost
```

或安装研究依赖：

```bash
uv sync --dev --extra research
```

### Optuna 依赖缺失

只有显式设置 `model.n_trials > 0` 时才需要 Optuna。缺依赖时安装：

```bash
uv sync --dev --extra tuning
```

或安装研究依赖：

```bash
uv sync --dev --extra research
```

### Legacy notebook 兼容预设缺列

`configs/preset/legacy_notebook_compat.yaml` 只用于复现早期 notebook 结果，依赖：

```text
pred_rel_return
```

处理：

- 补齐该列。
- 移除 legacy preset。
- 改回 `market.label_source=actual`。

### DolphinDB Python client 缺失

生成 Alpha101/191 时如果报：

```text
Missing optional DolphinDB Python client
```

处理：

```bash
uv sync --dev --extra external-alphas
```

普通 `moneytrees` 回测不需要该依赖；只有运行 `moneytrees-dolphindb-alphas` 时才需要。

### DolphinDB Alpha101/191 模块或 wrapper 预检失败

生成 Alpha101/191 时如果报：

```text
DolphinDB Alpha101/191 preflight failed
```

处理：

- 检查 `docker/dolphindb/modules/` 下是否有 `wq101alpha.dos`、`prepare101.dos`、`gtja191Alpha.dos`、`gtja191Prepare.dos` 和 `moneytreeAlpha.dos`。
- 使用 `docker-compose.alpha.yml` 时，确认该目录已挂载到 DolphinDB server 的 `/data/ddb/server/data/modules`。
- 确认 `moneytreeAlpha.dos` 定义了 `calcMoneyTreeAlpha101(rawData, startTime, endTime)` 和 `calcMoneyTreeAlpha191(rawData, startTime, endTime)`，或者命令中传入了正确的 `--alpha101-function` / `--alpha191-function`。
- 注意 `--wq101-module-version`、`--gtja191-module-version` 和 `--moneytree-alpha-module-version` 只记录 manifest 元数据，不会改变 DolphinDB `use` 的模块名。
- 先按 [DolphinDB Alpha101/191 外部因子生产](dolphindb_alpha101_191.md) 中的模块加载命令验证环境，再分阶段运行 `--alpha101`、`--alpha191`，最后同时写入正式 factor store。

### Alpha101/191 输出列不完整

报错通常包含：

```text
missing columns
unexpected alpha columns
```

处理：

- 检查 DolphinDB `moneytreeAlpha.dos` 包装函数是否返回宽表。
- 检查列名是否严格为 `alpha101_001...alpha101_101` 或 `alpha191_001...alpha191_191`。
- 检查是否只请求了一个 family，但 DolphinDB 返回了另一个 family 的 `alpha*_` 列。
- 检查 manifest 中记录的模块版本和字段映射。

## 结果归档检查

归档一次重要实验前，至少检查：

- `metrics.json` 存在且包含关键指标。
- `run_config.json` 包含 `git_commit`。
- `experiment_manifest.json` 存在，并包含输入文件 hash、schema hash、配置 hash 和运行环境。
- `run_summary.txt` 包含日期范围、segment 诊断和 holdout 信息。
- `strategy_nav.csv` 与 `benchmark_nav.csv` 日期有重叠。
- `oos_period_diagnostics.csv` 行数符合预期。
- 使用 holdout 时，`holdout/metrics.json` 和 `holdout/holdout_config.json` 存在。
- 数据输入文件和配置文件路径写入实验记录。
- 使用外部 Alpha101/191 时，保存 factor store manifest 或兼容 `.factor_manifest.json` 的 hash 和版本标签。

## 数据保存元数据

当前 raw parquet cache + `manifest.sqlite` + 标准面板 parquet + 回测产物的路线继续使用。已经落地：

- `request_hash`
- `params_json`
- `schema_hash`
- `content_hash`
- `created_at_utc`
- `updated_at_utc`
- `input_data_sha256`
- `resolved_config_hash`
- `output_schema_version`
- `experiment_manifest.json`

后续推荐新增派生数据目录：

```text
data/derived/
  cn_daily_panel/
    dataset_version=YYYYMMDD_or_hash/
      panel.parquet
      dataset_meta.json
```

`dataset_meta.json` 应记录 raw cache manifest 版本、生成参数、因子家族、复权口径、基准、代码 commit 和依赖版本。
