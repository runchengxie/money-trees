# money-tree

一个用于截面选股研究与回测的项目仓库。它保留了可复用的训练、回测、组合和评估骨架，并把市场适配层与模型选择层拆开，当前内置可运行的 `us` / `cn` 两条市场路径。

## Workflow

1. 先修改 `configs/market/*.yaml`，把 benchmark、标签口径和交易约束改成你自己的市场语义。
2. 按你的数据契约调整 `configs/market/*.yaml`，必要时再扩展 `src/treealpha/markets/*.py`。
3. 运行 smoke test，确认整条训练、回测和落盘链路正常。
4. 再开始增加特征、模型和更复杂的组合约束。

## First Files To Edit

- [pyproject.toml](/home/richard/code/money-tree/pyproject.toml)
  改项目名、描述和发布元数据。
- [configs/market/us.yaml](/home/richard/code/money-tree/configs/market/us.yaml)
  参考市场配置。
- [configs/market/cn.yaml](/home/richard/code/money-tree/configs/market/cn.yaml)
  A 股参考配置，包含 benchmark 和 tradability 过滤开关。
- [src/treealpha/markets/cn.py](/home/richard/code/money-tree/src/treealpha/markets/cn.py)
  A 股参考实现，可继续按你的数据契约扩展。
- [docs/minimal_run.md](/home/richard/code/money-tree/docs/minimal_run.md)
  最小跑通路径。

## Project Layout

- `src/treealpha/`
  package CLI、回测执行内核、模型 registry、市场 registry。
- `configs/market/*.yaml`
  市场适配占位层。
- `configs/model/*.yaml`
  `random_forest`、`xgboost`、`ridge`、`lasso`、`elasticnet` 的模型入口。
- `configs/backtest/*.yaml`
  默认运行参数和 smoke 参数。
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

常用命令直接通过 `uv run` 执行，不再依赖 `Makefile`。

默认 CLI 会按下面顺序叠配置：

- `configs/market/us.yaml`
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
  --config configs/market/us.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

也支持局部覆盖：

```bash
uv run moneytree \
  --config configs/market/us.yaml \
  --config configs/model/ridge.yaml \
  --config configs/backtest/default.yaml \
  --data data_small.parquet \
  --set backtest.segment1_windows=1 \
  --set backtest.segment2_windows=1
```

## Smoke Test

项目自带一个最小 smoke 配置和测试文件：

- [configs/backtest/smoke.yaml](/home/richard/code/money-tree/configs/backtest/smoke.yaml)
- [tests/test_smoke.py](/home/richard/code/money-tree/tests/test_smoke.py)

本地跑 smoke：

```bash
uv run moneytree \
  --config configs/market/us.yaml \
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
    us.yaml
    cn.yaml
  model/
    rf.yaml
    xgb.yaml
    ridge.yaml
    lasso.yaml
    elasticnet.yaml
```

多文件配置会按传入顺序做深合并，适合把市场、模型和回测参数拆开维护。

## Market Layer

- `us` 是可运行的参考实现，保留原有 SPY 相对收益输入与兼容输出。
- `cn` 是可运行的 A 股参考实现，需要 benchmark 列与 tradability 列契约。
- 市场 profile 负责三件事：
  benchmark 别名、标签列约束、可交易过滤。

## Model Layer

- `random_forest`
  保留原项目的树模型主路径。
- `xgboost`
  通过可选依赖启用，未安装时会 fail fast。
- `ridge` / `lasso` / `elasticnet`
  作为线性基准，默认关闭特征选择和调参。

## Outputs

默认运行会生成这些核心产物：

- `metrics.json`
- `run_config.json`
- `run_summary.txt`
- `strategy_nav.csv`
- `benchmark_nav.csv`
- `strategy_returns.csv`
- `benchmark_returns.csv`
- `strategy_turnover.csv`
- `active_names.csv`
- `ic_series.csv`
- `oos_period_diagnostics.csv`
- `strategy_vs_benchmark.csv`
- `segment_a_features.txt`
- `segment_b_features.txt`
- 可选 `holdout/`

对 `us` 路径，当前仍会额外保留 `spy_nav.csv`、`spy_returns.csv`、`strategy_vs_spy.csv` 作为兼容别名。
