# Runbook

Runbook 记录日常执行、排障和归档检查。常见使用示例见 [cookbook.md](cookbook.md)。

## 日常运行顺序

1. 更新依赖。

```bash
uv sync --dev --extra research
```

2. 刷新 TuShare raw cache。

```bash
uv run moneytree-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily_alpha.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --benchmark 000300.SH \
  --factor-family alpha158 \
  --factor-family alpha360
```

3. 可选：离线生成外部 Alpha101/191。

Alpha101/191 需要先由 DolphinDB 等外部生产器生成后并入面板。详细 WSL/Docker 和 DolphinDB 模块说明见 [dolphindb_alpha101_191.md](dolphindb_alpha101_191.md)。

```bash
uv pip install dolphindb

uv run python scripts/build_dolphindb_alphas.py \
  --input data/cn_daily_alpha.parquet \
  --output data/cn_daily_alpha_all.parquet \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --password 123456 \
  --alpha101 \
  --alpha191 \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

生成后检查：

```bash
test -f data/cn_daily_alpha_all.parquet
test -f data/cn_daily_alpha_all.parquet.factor_manifest.json
```

4. 跑主回测。

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha.parquet \
  --output-dir artifacts/xgb-alpha-daily
```

如果使用外部 Alpha101/191，把 `--data` 改成生成后的面板：

```text
data/cn_daily_alpha_all.parquet
```

5. 检查输出。

```bash
test -f artifacts/xgb-alpha-daily/metrics.json
test -f artifacts/xgb-alpha-daily/run_config.json
test -f artifacts/xgb-alpha-daily/run_summary.txt
```

6. 跑测试。

```bash
uv run pytest -q
```

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
uv run moneytree-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20
```

接口字段口径变化或 cache 明显损坏时，可以对特定 API 或日期做定向清理后重拉。清理前先确认没有其他实验依赖同一缓存目录。

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

### Notebook 兼容预设缺列

`configs/preset/notebook_compat.yaml` 依赖：

```text
pred_rel_return
```

处理：

- 补齐该列。
- 移除 `configs/preset/notebook_compat.yaml`。
- 改回 `market.label_source=actual`。

### DolphinDB Python client 缺失

生成 Alpha101/191 时如果报：

```text
Missing optional DolphinDB Python client
```

处理：

```bash
uv pip install dolphindb
```

普通 `moneytree` 回测不需要该依赖；只有运行 `scripts/build_dolphindb_alphas.py` 时才需要。

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
- 使用外部 Alpha101/191 时，保存对应 `.factor_manifest.json` 的 hash 和版本标签。

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
