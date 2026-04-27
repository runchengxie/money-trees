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

3. 跑主回测。

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha.parquet \
  --output-dir artifacts/xgb-alpha-daily
```

4. 检查输出。

```bash
test -f artifacts/xgb-alpha-daily/metrics.json
test -f artifacts/xgb-alpha-daily/run_config.json
test -f artifacts/xgb-alpha-daily/run_summary.txt
```

5. 跑测试。

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
