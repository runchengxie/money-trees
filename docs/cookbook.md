# Cookbook

Cookbook 记录常见任务的可复制做法，重点是“怎么用”。Runbook 记录日常运行、失败恢复和归档检查，重点是“怎么稳地执行”。排障流程见 [runbook.md](runbook.md)。

## 1. 跑最小本地回测

准备一个满足 [data_contract.md](data_contract.md) 的 parquet 文件后运行：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data data_small.parquet \
  --output-dir artifacts/smoke
```

调试时建议减少滚动窗口和调参次数：

```bash
uv run moneytree \
  --data data_small.parquet \
  --output-dir artifacts/debug \
  --set model.feature_selection=none \
  --set model.n_trials=0 \
  --set backtest.segment1_windows=1 \
  --set backtest.segment2_windows=1
```

## 2. 使用本地模板预设

`configs/preset/template_smoke.yaml` 已写入：

```yaml
market:
  data_path: ./data_small.parquet

output:
  output_dir: ./artifacts/template-smoke
```

运行：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --config configs/preset/template_smoke.yaml
```

## 3. 从 TuShare 拉日频面板

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
uv run moneytree-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --benchmark 000300.SH
```

`--cache-dir` 会缓存 `daily`、`daily_basic`、`adj_factor`、`stk_limit` 和 `suspend_d` 的原始返回。重复拉取同一区间时，已有交易日会读本地 parquet。

## 4. 拉 TuShare 并追加 Alpha158/360

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

默认优先使用复权价格生成本地 Alpha 特征。使用未复权价格：

```bash
uv run moneytree-tushare \
  --start-date 20200101 \
  --end-date 20241231 \
  --output data/cn_daily_alpha_raw.parquet \
  --factor-family alpha158 \
  --raw-features
```

## 5. 跑 XGBoost 回归模型

```bash
uv sync --dev --extra research

uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha.parquet \
  --output-dir artifacts/xgb-alpha-daily
```

`xgb_regressor` 训练目标是 `rel_return`，输出连续 score 后进入组合构建。

## 6. 切换线性模型基准

Ridge：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/ridge.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha.parquet \
  --output-dir artifacts/ridge-alpha-daily
```

Lasso 和 ElasticNet 只需要替换模型配置：

```text
configs/model/lasso.yaml
configs/model/elasticnet.yaml
```

线性模型训练目标是 `rel_return`，当前不支持调参和特征选择。

## 7. 使用 signal-risk QP 组合

默认组合方法是 `heuristic`。切到 QP：

```bash
uv run moneytree \
  --data data_small.parquet \
  --output-dir artifacts/qp \
  --set portfolio.weighting_method=signal_risk_qp \
  --set portfolio.qp_turnover_penalty=10 \
  --set portfolio.qp_risk_aversion=20
```

QP 会用训练窗口 `next_period_return` 估计协方差。求解失败时默认回退到启发式权重。

## 8. 跑最终 holdout

```bash
uv run moneytree \
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

## 9. Notebook 兼容路径

Notebook 兼容预设会：

- 使用 `pred_rel_return` 作为标签来源。
- 将 `feature_lag_periods` 设为 `0`。
- 使用 `notebook_compat` 特征选择路径。
- 将交易成本设为 `0`。

命令：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --config configs/preset/notebook_compat.yaml \
  --data data_small.parquet \
  --output-dir artifacts/notebook-compat
```

输入数据必须包含 `pred_rel_return`。

## 10. 单因子 IC 诊断

```python
import pandas as pd
from moneytree.factors import compute_factor_ic, summarize_factor_ic

frame = pd.read_parquet("data/cn_daily_alpha.parquet")
ic = compute_factor_ic(frame, ["alpha158_kmid", "alpha158_roc_20"])
summary = summarize_factor_ic(ic)
print(summary)
```

`compute_factor_ic` 默认使用 `next_period_return` 作为收益列，按日期计算截面 IC 和 RankIC。
