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
  --benchmark 000300.SH
```

`--cache-dir` 会缓存 `daily`、`daily_basic`、`adj_factor`、`stk_limit` 和 `suspend_d` 的原始返回。重复拉取同一区间时，已有交易日会读本地 parquet。

## 3. 生成本地 Alpha158/360，共 518 个特征

```bash
uv run moneytrees-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily_alpha158_360.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --benchmark 000300.SH \
  --factor-family alpha158 \
  --factor-family alpha360
```

默认优先使用复权价格生成本地 Alpha 特征。使用未复权价格：

```bash
uv run moneytrees-tushare \
  --start-date 20200101 \
  --end-date 20241231 \
  --output data/cn_daily_alpha_raw.parquet \
  --factor-family alpha158 \
  --raw-features
```

## 4. 用 DolphinDB 补齐 Alpha101/191，共 292 个外部列

Alpha101/191 不在项目内本地计算。推荐先用 DolphinDB 离线生成，再并入标准 `date, ticker` 面板。详细环境和口径见 [dolphindb_alpha101_191.md](dolphindb_alpha101_191.md)。

安装外部 Alpha 依赖：

```bash
uv sync --dev --extra external-alphas
```

生成并合并 Alpha101/191：

```bash
uv run moneytrees-dolphindb-alphas \
  --input data/cn_daily_alpha158_360.parquet \
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

旁路 manifest 默认写到：

```text
data/cn_daily_alpha_all.parquet.factor_manifest.json
```

## 5. 使用完整 810 因子面板跑 XGBoost 回归

```bash
uv sync --dev --extra research

uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha_all.parquet \
  --output-dir artifacts/xgb-alpha-all
```

`xgb_regressor` 训练目标是 `rel_return`，输出连续 score 后进入组合构建。

## 6. 单因子 IC / RankIC 诊断

```python
import pandas as pd
from moneytree.factors import compute_factor_ic, summarize_factor_ic

frame = pd.read_parquet("data/cn_daily_alpha158_360.parquet")
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
  --data data/cn_daily_alpha158_360.parquet \
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
  --data data/cn_daily_alpha_all.parquet \
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
