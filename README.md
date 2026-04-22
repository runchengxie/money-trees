# Treealpha Template Scaffold

一个从美股随机森林研究仓库抽出来的可复用截面选股脚手架。当前默认保留 `us` 市场配置作为参考实现，但仓库结构已经改成更适合继续孵化 `tree-alpha-cn` 这类衍生项目的模板形态。

## 当前定位

- 默认入口已经切到 package CLI：`treealpha.cli.backtest`
- 模型层通过 registry 选择：`random_forest`、`xgboost`、`ridge`、`lasso`、`elasticnet`
- 市场层通过 profile 选择：当前内置 `us`
- 旧 `scripts/run_backtest.py` 仍保留，但现在只是兼容包装层
- 历史 artifacts 和参考 notebook 已移到 `examples/`，不再属于默认工作流

## 快速开始

环境：

- Python `>=3.10`
- 依赖管理器：`uv`

安装：

```bash
uv sync --dev
```

使用默认参考配置运行：

```bash
uv run python -m treealpha.cli.backtest \
  --config configs/reference_us_random_forest.toml \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

也可以直接使用 console script：

```bash
uv run treealpha-backtest \
  --config configs/reference_us_random_forest.toml \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

兼容旧入口：

```bash
uv run python scripts/run_backtest.py \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

## 配置结构

参考配置见 [configs/reference_us_random_forest.toml](/home/richard/code/guan-random-forest-cross-sectional/configs/reference_us_random_forest.toml)。

主要分为 5 层：

- `market`：市场 profile、标签构造、数据路径、feature lag
- `model`：模型 id、默认参数、调参与特征选择
- `portfolio`：信号转仓位、QP 风险约束、行业中性等
- `backtest`：滚动窗口、成本、segment、holdout
- `output`：输出目录与可选 parquet 导出

CLI 支持用 `--set dotted.path=value` 做小范围覆盖，例如：

```bash
uv run python -m treealpha.cli.backtest \
  --config configs/reference_us_random_forest.toml \
  --data data_small.parquet \
  --set model.id=ridge \
  --set model.n_trials=0 \
  --set model.feature_selection=none
```

## 包结构

```text
src/treealpha/
  cli/          # package CLI
  markets/      # market profile registry + implementations
  models/       # model adapter registry + implementations
  backtest.py   # walk-forward backtest core
  data.py       # panel loading / preprocessing helpers
  portfolio.py  # score -> weights / turnover / PnL
  runner.py     # shared execution kernel for package CLI and legacy script
```

## 内置能力

### Models

- `random_forest`：保留原项目的 RF 调参与特征选择流程
- `xgboost`：作为可选依赖接入，未安装时会 fail fast
- `ridge` / `lasso` / `elasticnet`：线性基准模型，默认不支持 RF 式调参与特征选择

### Market Profiles

- `us`：把原来的 SPY 相对收益标签和 benchmark 逻辑抽成 profile
- profile 可以通过 registry 扩展，衍生仓库可以直接注册 `cn` 等新市场

## 数据约定

当前 `us` profile 仍需要原始数据包含：

- `date`
- `ticker`
- `next_period_return`
- `spy_cum_ret`
- `spy_next_period_return` 或 `pred_rel_return`（取决于 `label_source`）

profile 会在预处理阶段补齐通用 benchmark 别名：

- `benchmark_cum_ret`
- `benchmark_next_period_return`

这让回测和评估层不再直接写死 SPY 列名。

## 输出产物

默认输出仍保持原项目的核心合同：

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
- 可选 `holdout/` 目录

## 扩展新市场/新仓库

如果你要基于这个仓库继续做 `tree-alpha-cn`：

1. 新增 `cn` market profile 并注册
2. 在新仓库里放自己的默认 config
3. 按 A 股数据语义重定义 benchmark / label / tradability filter
4. 保持 `treealpha` 的 runner、portfolio、metrics 作为底层复用层

## Legacy 内容

以下内容已从默认模板工作流移出：

- [examples/legacy_artifacts](/home/richard/code/guan-random-forest-cross-sectional/examples/legacy_artifacts)
- [examples/reference_notebook](/home/richard/code/guan-random-forest-cross-sectional/examples/reference_notebook)

它们保留为历史参考，不再作为模板主入口的一部分。
