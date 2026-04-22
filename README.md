# Treealpha Template Scaffold

一个用于孵化截面选股项目的模板仓库。它保留了可复用的训练、回测、组合和评估骨架，并把市场适配层与模型选择层拆开，适合继续衍生 `tree-alpha-cn`、`tree-alpha-us` 这类独立仓库。

## Template Workflow

1. 用这个仓库生成一个新仓库。
2. 先修改 `configs/market/*.yaml`，把 benchmark、标签口径和交易约束占位符改成你自己的市场语义。
3. 替换 `src/treealpha/markets/*.py`，让 market profile 和你的数据契约一致。
4. 运行 smoke test，确认脚手架还能完整训练、回测并落盘。
5. 再开始增加特征、模型和更复杂的组合约束。

## First Files To Edit

- [pyproject.toml](/home/richard/code/guan-random-forest-cross-sectional/pyproject.toml)
  改项目名、描述和发布元数据。
- [configs/market/us.yaml](/home/richard/code/guan-random-forest-cross-sectional/configs/market/us.yaml)
  参考市场配置。
- [configs/market/cn.yaml](/home/richard/code/guan-random-forest-cross-sectional/configs/market/cn.yaml)
  A 股占位配置。
- [src/treealpha/markets/cn.py](/home/richard/code/guan-random-forest-cross-sectional/src/treealpha/markets/cn.py)
  模板占位实现，默认会明确报错提醒你替换。
- [examples/minimal_run.md](/home/richard/code/guan-random-forest-cross-sectional/examples/minimal_run.md)
  最小跑通路径。

## What The Template Includes

- `src/treealpha/`
  package CLI、回测执行内核、模型 registry、市场 registry。
- `configs/market/*.yaml`
  市场适配占位层。
- `configs/model/*.yaml`
  `random_forest`、`xgboost`、`ridge`、`lasso`、`elasticnet` 的模型入口。
- `configs/backtest/*.yaml`
  默认运行参数和 smoke 参数。
- `tests/`
  单元测试和模板 smoke test。
- `scripts/convert_pickle_to_parquet.py`
  一个保留的本地数据转换小工具。

## Quick Start

环境要求：

- Python `>=3.10`
- `uv`

安装依赖：

```bash
uv sync --dev
```

默认 CLI 会按下面顺序叠配置：

- `configs/market/us.yaml`
- `configs/model/rf.yaml`
- `configs/backtest/default.yaml`

直接运行：

```bash
uv run treealpha-backtest \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

显式传入配置也可以，后面的文件会覆盖前面的同名字段：

```bash
uv run treealpha-backtest \
  --config configs/market/us.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

也支持局部覆盖：

```bash
uv run treealpha-backtest \
  --config configs/market/us.yaml \
  --config configs/model/ridge.yaml \
  --config configs/backtest/default.yaml \
  --data data_small.parquet \
  --set backtest.segment1_windows=1 \
  --set backtest.segment2_windows=1
```

## Smoke Test

模板自带一个最小 smoke 配置和测试文件：

- [configs/backtest/smoke.yaml](/home/richard/code/guan-random-forest-cross-sectional/configs/backtest/smoke.yaml)
- [tests/test_smoke.py](/home/richard/code/guan-random-forest-cross-sectional/tests/test_smoke.py)

本地跑 smoke：

```bash
make smoke DATA=./data_small.parquet OUTPUT=./artifacts/template-smoke
```

跑完整测试：

```bash
make test
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

- `us` 是当前唯一可运行的参考实现，保留原有 SPY 相对收益语义。
- `cn` 已注册为模板占位 profile，但默认会抛出明确错误，提醒你先替换 A 股数据契约。
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
- `spy_nav.csv`
- `strategy_returns.csv`
- `spy_returns.csv`
- `strategy_turnover.csv`
- `active_names.csv`
- `ic_series.csv`
- `oos_period_diagnostics.csv`
- `strategy_vs_spy.csv`
- `segment_a_features.txt`
- `segment_b_features.txt`
- 可选 `holdout/`
