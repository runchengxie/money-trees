# money-tree

一个用于 A 股截面选股研究与回测的项目仓库。它保留了可复用的训练、回测、组合和评估骨架，并把市场适配层与模型选择层拆开；当前内置路径只维护 A 股 `cn` profile。

## Workflow

1. 先修改 `configs/market/cn.yaml`，把 benchmark、标签口径和交易约束改成你的数据语义。
2. 按你的数据契约调整列名映射，必要时再扩展 [src/moneytree/markets/cn.py](/home/richard/code/money-tree/src/moneytree/markets/cn.py)。
3. 运行 smoke test，确认训练、回测和落盘链路正常。
4. 再开始增加特征、模型和更复杂的组合约束。

## First Files To Edit

- [configs/market/cn.yaml](/home/richard/code/money-tree/configs/market/cn.yaml)
  A 股市场配置，包含 benchmark 列、标签口径和 tradability 过滤开关。
- [configs/preset/template_smoke.yaml](/home/richard/code/money-tree/configs/preset/template_smoke.yaml)
  本地模板运行配置，替代 `.env.example` 里的非密钥运行参数。
- [src/moneytree/markets/cn.py](/home/richard/code/money-tree/src/moneytree/markets/cn.py)
  A 股 market profile 实现，可继续按你的数据契约扩展。
- [docs/minimal_run.md](/home/richard/code/money-tree/docs/minimal_run.md)
  最小跑通路径。
- [docs/daily_alpha_research.md](/home/richard/code/money-tree/docs/daily_alpha_research.md)
  A 股日频 Alpha101/191/158/360、TuShare 拉取和 XGBoost regressor 说明。

## Project Layout

- `src/moneytree/`
  package CLI、回测执行内核、模型 registry、市场 registry。
- `configs/market/cn.yaml`
  A 股市场适配层。
- `configs/model/*.yaml`
  `random_forest`、`xgboost`、`xgboost_regressor`、`ridge`、`lasso`、`elasticnet` 的模型入口。
- `configs/backtest/*.yaml`
  默认运行参数和 smoke 参数。
- `configs/preset/*.yaml`
  可叠加的运行 preset。
- `tests/`
  单元测试和 smoke test。
- `project_tools/`
  仓库级辅助脚本。

## Quick Start

环境要求：

- Python `>=3.10`
- `uv`

安装依赖：

```bash
uv sync --dev
```

默认 CLI 会按下面顺序叠配置：

- `configs/market/cn.yaml`
- `configs/model/rf.yaml`
- `configs/backtest/default.yaml`

直接运行：

```bash
uv run moneytree \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

显式传入配置也可以，后面的文件会覆盖前面的同名字段：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

也支持局部覆盖：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/ridge.yaml \
  --config configs/backtest/default.yaml \
  --data data_small.parquet \
  --set backtest.segment1_windows=1 \
  --set backtest.segment2_windows=1
```

模板 smoke preset 示例：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --config configs/preset/template_smoke.yaml
```

notebook 兼容 preset 示例：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --config configs/preset/notebook_compat.yaml \
  --data data_small.parquet \
  --output-dir artifacts/notebook-compat
```

这个 preset 依赖输入数据里存在 `pred_rel_return` 列。

日频 Alpha + XGBoost regressor 示例：

```bash
uv sync --dev --extra research

uv run moneytree-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily_alpha.parquet \
  --benchmark 000300.SH \
  --factor-family alpha158 \
  --factor-family alpha360

uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha.parquet \
  --output-dir artifacts/xgb-alpha-daily
```

## Smoke Test

项目自带一个最小 smoke 配置和测试文件：

- [configs/backtest/smoke.yaml](/home/richard/code/money-tree/configs/backtest/smoke.yaml)
- [tests/test_smoke.py](/home/richard/code/money-tree/tests/test_smoke.py)

本地跑 smoke：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data ./data_small.parquet \
  --output-dir ./artifacts/smoke
```

跑完整测试：

```bash
uv run pytest -q
```

## Config Layout

```text
configs/
  backtest/
    default.yaml
    smoke.yaml
  market/
    cn.yaml
  model/
    rf.yaml
    xgb.yaml
    xgb_regressor.yaml
    ridge.yaml
    lasso.yaml
    elasticnet.yaml
  preset/
    notebook_compat.yaml
    template_smoke.yaml
```

多文件配置会按传入顺序做深合并，适合把市场、模型和回测参数拆开维护。

## Market Layer

- `cn` 是当前唯一内置 profile，需要 benchmark 列与 tradability 列契约。
- 市场 profile 负责三件事：
  benchmark 别名、标签列约束、可交易过滤。

默认 benchmark 配置是 `000300.SH`，输入数据默认使用：

- `benchmark_next_period_return`
- `benchmark_cum_ret`

可交易过滤默认由 `configs/market/cn.yaml` 控制：

- `is_suspended`
- `is_st`
- `hit_up_limit`
- `hit_down_limit`

## Model Layer

- `random_forest`
  保留树模型主路径。
- `xgboost`
  通过可选依赖启用，未安装时会 fail fast。
- `xgboost_regressor`
  通过可选依赖启用，使用连续 `rel_return` 作为训练目标，适合日频多因子回归研究。
- `ridge` / `lasso` / `elasticnet`
  作为线性基准，默认关闭特征选择和调参。

## Outputs

默认运行会生成这些核心产物：

- `metrics.json`
- `run_config.json`
- `run_summary.txt`
- `strategy_nav.csv`
- `signal_nav.csv`
- `benchmark_nav.csv`
- `strategy_returns.csv`
- `benchmark_returns.csv`
- `signal_profit.csv`
- `strategy_turnover.csv`
- `active_names.csv`
- `ic_series.csv`
- `oos_period_diagnostics.csv`
- `strategy_vs_benchmark.csv`
- `notebook_report_navs.csv`
- `notebook_rolling_beta.csv`
- `notebook_residual_returns.csv`
- `notebook_residual_distribution.csv`
- `segment_a_features.txt`
- `segment_b_features.txt`
- 可选 `segment_a_selection_history.csv`
- 可选 `segment_b_selection_history.csv`
- 可选 `segment_a_feature_score_curve.csv`
- 可选 `segment_b_feature_score_curve.csv`
- 可选 `holdout/`
