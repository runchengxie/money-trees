# Cookbook

Cookbook 记录常见任务的可复制做法，重点是“怎么用”。Runbook 记录日常运行、失败恢复和归档检查，重点是“怎么稳地执行”。排障流程见 [runbook.md](runbook.md)。

## 1. 跑最小本地回测

准备一个满足 [data_contract.md](data_contract.md) 的 parquet 文件后运行：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data data_small.parquet \
  --output-dir artifacts/smoke
```

调试时建议减少滚动窗口，并保持调参关闭：

```bash
uv run moneytrees \
  --data data_small.parquet \
  --output-dir artifacts/debug \
  --set model.feature_selection=none \
  --set model.n_trials=0 \
  --set backtest.segment1_windows=1 \
  --set backtest.segment2_windows=1
```

## 2. 从 TuShare 拉日频面板

安装研究依赖：

```bash
uv sync --dev --extra research
```

设置 token：

```bash
export TUSHARE_TOKEN=your_token
```

拉取日频数据：

```bash
uv run moneytrees-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --progress \
  --benchmark 000300.SH
```

`--cache-dir` 会缓存 `daily`、`daily_basic`、`adj_factor`、`stk_limit` 和 `suspend_d` 的原始返回。重复拉取同一区间时，已有交易日会读本地 parquet。长区间全市场任务建议加 `--progress`，观察每个接口的交易日进度、累计行数、cache 命中和实际请求次数。

生成基础面板后先做只读质量检查：

```bash
uv run moneytrees-data-status \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --raw-cache data/raw/tushare \
  --mode warn
```

这个检查会流式扫描 parquet 面板，检查 `date,ticker`、关键列空值、派生收益一致性、复权列一致性，并检查 raw cache 中 `daily` 有行但 `adj_factor` 或 `daily_basic` 空分片的问题。收益列只允许自然边界空值：每个 ticker 的首尾以及基准首尾交易日。

## 3. 按需生成本地 Alpha158/360 factor store

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

基础面板生成后，再按需生成本地因子族。factor store 会把基础面板和因子族分开保存，避免把所有列写进单个超宽 parquet。

回测从因子仓库读取选中特征时，缺失列默认报错。迁移旧数据时可以临时设置：

```bash
uv run moneytrees \
  --data data/factor_store/cn_daily/manifest.json \
  --set features.missing_feature_policy=warn_fill_zero
```

```bash
uv run moneytrees-factor-store \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output-dir data/factor_store/cn_daily \
  --factor-family alpha158 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --progress
```

默认优先使用复权价格生成本地 Alpha 特征，并把生成的 `alpha158_`、`alpha360_` 列保存为 `float32`。需要保留双精度时传 `--factor-dtype float64`。使用未复权价格：

当 `--input` 是 parquet 时，`moneytrees-factor-store` 会按 `--chunk-trade-dates` 分区流式读取面板，并自动带上 Alpha158/360 所需的历史 overlap。大面板内存紧张时，优先把 `--chunk-trade-dates` 调低到 `20` 或 `10`，不要把因子重新并回单个超宽 parquet。

```bash
uv run moneytrees-factor-store \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output-dir data/factor_store/cn_daily_raw_factor \
  --factor-family alpha158 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --progress \
  --raw-features
```

`--raw-features` 只表示本地 Alpha158/360 使用未复权价格生成，不会减少 TuShare 接口拉取量。

回测时可直接把 factor store manifest 作为数据入口，并用配置限定实际加载的因子族：

```bash
uv run moneytrees \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/ridge-alpha158-only \
  --set 'features.include_factor_families=["alpha158"]'
```

轻量调试时只生成 Alpha158：

```bash
uv run moneytrees-factor-store \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output-dir data/factor_store/debug_alpha158 \
  --factor-family alpha158 \
  --chunk-trade-dates 20 \
  --progress
```

## 4. 用 DolphinDB 补齐 Alpha101/191，共 292 个外部列

Alpha101/191 不在项目内本地计算。推荐先用 DolphinDB 离线生成，再写入同一个 factor store。详细环境和口径见 [generate_alpha101_191_with_dolphindb.md](generate_alpha101_191_with_dolphindb.md)。

parquet 输入配合 `--no-wide-output` 时，外部 Alpha CLI 默认用 `--stream-input auto` 按目标交易日和 warmup 窗口分片读取、上传、计算和落盘，避免完整输入面板一次性进入内存。宽表输出或显式 `--stream-input off` 仍会走完整输入上传路径；先用小样本分别跑 `--alpha101` 和 `--alpha191` 冒烟测试，正式生成时优先按 family 分开运行。

安装外部 Alpha 依赖：

```bash
uv sync --dev --extra external-alphas
```

生成 Alpha101/191 并写入 factor store：

```bash
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
  --stream-input auto \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

兼容旧宽表路径时仍可传 `--output data/cn_daily_alpha_all.parquet`。factor store 路径的 manifest 写到：

```text
data/factor_store/cn_daily/manifest.json
```

## 5. 使用完整 810 因子 factor store 跑 XGBoost 回归

```bash
uv sync --dev --extra research

uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/xgb-alpha-all \
  --set backtest.memory_budget_gb=32
```

`xgb_regressor` 训练目标是 `rel_return`，输出连续 score 后进入组合构建。
默认 `backtest.load_mode: auto` 会按回测日期裁剪读取，并在读取因子仓库前做内存预检。如果完整 810 因子估算超预算，先按因子族分批跑，不要切到 `backtest.load_mode=full` 硬跑。

调试模型时可以只读取某个因子族，避免把完整 810 因子都读入内存：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/ridge.yaml \
  --config configs/backtest/default.yaml \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/ridge-alpha158-only \
  --set 'features.include_factor_families=["alpha158"]'
```

也可以直接用前缀：

```bash
uv run moneytrees \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/debug-alpha360 \
  --set 'features.include_factor_prefixes=["alpha360_"]' \
  --set model.feature_selection=none \
  --set model.n_trials=0
```

## 6. 单因子 IC / RankIC 诊断

```python
import pandas as pd
from moneytree.factor_store import load_factor_store
from moneytree.factors import compute_factor_ic, summarize_factor_ic

frame = load_factor_store(
    "data/factor_store/cn_daily/manifest.json",
    include_factor_families=["alpha158"],
)
ic = compute_factor_ic(frame, ["alpha158_kmid", "alpha158_roc_20"])
summary = summarize_factor_ic(ic)
print(summary)
```

`compute_factor_ic` 默认使用 `next_period_return` 作为收益列，按日期计算截面 IC 和 RankIC。

## 7. 切换线性模型基准

Ridge：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/ridge.yaml \
  --config configs/backtest/default.yaml \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/ridge-alpha-daily
```

Lasso 和 ElasticNet 只需要替换模型配置：

```text
configs/model/lasso.yaml
configs/model/elasticnet.yaml
```

线性模型训练目标是 `rel_return`，当前不支持调参和特征选择。

## 8. 显式开启随机森林调参

默认模型配置不调参。需要 Optuna 时叠加 tuning 预设：

```bash
uv sync --dev --extra tuning

uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --config configs/preset/tuning.yaml \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/rf-alpha-all-tuned
```

## 9. 使用 signal-risk QP 组合

默认组合方法是 `heuristic`。切到 QP：

```bash
uv run moneytrees \
  --data data_small.parquet \
  --output-dir artifacts/qp \
  --set portfolio.weighting_method=signal_risk_qp \
  --set portfolio.qp_turnover_penalty=10 \
  --set portfolio.qp_risk_aversion=20
```

QP 会用训练窗口 `next_period_return` 估计协方差。求解失败时默认回退到启发式权重。

## 10. 跑最终 holdout

```bash
uv run moneytrees \
  --data data_small.parquet \
  --output-dir artifacts/holdout-check \
  --set backtest.holdout.start=2015-01-01 \
  --set backtest.holdout.end=2015-12-31 \
  --set backtest.holdout.model_segment=segment_b
```

holdout 结果写到：

```text
artifacts/holdout-check/holdout/
```

## 11. 使用本地模板预设

`configs/preset/template_smoke.yaml` 已写入：

```yaml
market:
  data_path: ./data_small.parquet

output:
  output_dir: ./artifacts/template-smoke
```

运行：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --config configs/preset/template_smoke.yaml
```

## 12. 迁移旧 pickle 数据

`scripts/convert_pickle_to_parquet.py` 是迁移工具，不属于主研究路径：

```bash
uv run python scripts/convert_pickle_to_parquet.py \
  --input data_small.pkl
```

## 13. Legacy notebook 复现

`configs/preset/legacy_notebook_compat.yaml` 只用于复现早期 notebook 结果，不建议用于正式 Alpha101/191/158/360 因子研究。该预设会：

- 使用 `pred_rel_return` 作为标签来源。
- 将 `feature_lag_periods` 设为 `0`。
- 使用 `notebook_compat` 特征选择路径。
- 将交易成本设为 `0`。
- 启用 200 次随机森林调参。

命令：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --config configs/preset/legacy_notebook_compat.yaml \
  --data data_small.parquet \
  --output-dir artifacts/legacy-notebook-compat
```

输入数据必须包含 `pred_rel_return`。
