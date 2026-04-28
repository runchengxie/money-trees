# money-trees 摇钱树

> A dollar might turn to a million and we all rich\ 
> That's just how I feel
> 
> 一块钱也能滚成一百万，兄弟们都能富起来我心里就是这么觉得\ 
> 我心里就是这么觉得
> 
> *Kendrick Lamar - Money Trees*
> 
> *肯德里克·拉马尔 - 摇钱树*

`money-trees` / Money Trees 是一个面向 A 股截面选股研究的经典 Alpha 因子、训练、回测和结果归档工具。项目围绕 Alpha101、Alpha191、Alpha158 和 Alpha360 共 810 个经典因子的标准列契约展开：Alpha158/360 共 518 个特征在本地生成，Alpha101/191 共 292 个特征由 DolphinDB 等外部生产器离线生成后并入标准 `date, ticker` 面板。核心链路包括 TuShare 日频数据拉取、因子生成/并入、特征滞后、模型适配器、组合构建、滚动回测、holdout 验证和可复现产物输出。

Python import 包名仍然是 `moneytree`，旧的 `moneytree` CLI 也继续可用；新文档优先使用 `moneytrees` CLI alias。

## 使用路径

1. 最小回测：使用已有标准 `date, ticker` 面板运行模型和组合回测。
2. 本地 518 因子：通过 TuShare 生成基础面板，并追加 Alpha158/360。
3. 完整 810 因子：先生成 Alpha158/360，再用 DolphinDB 离线生成 Alpha101/191，合并后进入统一回测链路。

## 快速开始

环境要求：

- Python `>=3.10`
- `uv`

安装开发依赖：

```bash
uv sync --dev
```

运行最小回测：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data data_small.parquet \
  --output-dir artifacts/smoke
```

拉取 TuShare 日频数据并追加本地 Alpha158/360：

```bash
uv sync --dev --extra research

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

追加外部 Alpha101/191，得到完整 810 因子面板：

```bash
uv sync --dev --extra external-alphas

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

使用完整面板跑 XGBoost 回归：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha_all.parquet \
  --output-dir artifacts/xgb-alpha-all
```

显式开启随机森林调参：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --config configs/preset/tuning.yaml \
  --data data/cn_daily_alpha_all.parquet \
  --output-dir artifacts/rf-alpha-all-tuned
```

## 常用命令

```bash
uv run pytest -q
```

```bash
uv run ruff check .
```

```bash
uv run pytest -q tests/test_smoke.py tests/test_backtest_cli.py
```

## 文档导航

- [docs/minimal_run.md](docs/minimal_run.md): 最小跑通路径和最小数据列。
- [docs/architecture.md](docs/architecture.md): 数据层、市场层、因子层、模型层、组合层、回测层和输出层设计。
- [docs/data_contract.md](docs/data_contract.md): 标准面板索引、必需列、可选列、标签和特征口径。
- [docs/configuration.md](docs/configuration.md): 配置文件分层、合并规则和常用字段。
- [docs/outputs.md](docs/outputs.md): `metrics.json`、`run_config.json`、CSV 和 holdout 产物说明。
- [docs/cookbook.md](docs/cookbook.md): 常见研究任务示例。
- [docs/runbook.md](docs/runbook.md): 日常运行、缓存刷新、排障和归档检查。
- [docs/testing.md](docs/testing.md): 测试命令、测试覆盖和当前测试缺口。
- [docs/daily_alpha_research.md](docs/daily_alpha_research.md): Alpha101/191/158/360 日频研究说明。
- [docs/factor_catalog.md](docs/factor_catalog.md): 因子列级清单说明，机器可读版本在 [docs/factor_catalog.csv](docs/factor_catalog.csv)。
- [docs/dolphindb_alpha101_191.md](docs/dolphindb_alpha101_191.md): DolphinDB 外部 Alpha101/191 生产说明。
- [docs/maintenance.md](docs/maintenance.md): 维护 backlog、迁移工具和后续重构候选项。

## 项目结构

```text
configs/
  backtest/   回测窗口、成本、holdout 和输出配置
  market/     A 股市场配置
  model/      内置模型入口配置
  preset/     可叠加的本地运行预设
docs/         使用、架构、数据契约和运维文档
project_tools/ 仓库维护脚本
scripts/      兼容 wrapper 和迁移脚本
src/moneytree/ 核心包、CLI、数据层、模型、组合和回测逻辑
tests/        单元测试、CLI 冒烟测试和数据源测试
```

## 当前边界

- 市场层只有 `cn` 市场配置档，默认基准是 `000300.SH`。
- 输入数据支持 pickle 和 parquet，推荐统一为 `date, ticker` MultiIndex parquet。
- Alpha158/360 是本地生成的日频特征；Alpha101/191 是外部生成后并入标准面板的列契约。
- DolphinDB、TuShare、XGBoost 和 Optuna 都是可选依赖；普通回测只需要已有标准面板。
- A 股历史 ST、历史行业归属、退市股票完整样本和幸存者偏差需要在上游数据治理中解决。
- 当前数据保存路线是 raw parquet cache + `manifest.sqlite` + 可重建标准面板 + 回测产物；回测会生成 `experiment_manifest.json`，TuShare cache manifest 会记录请求、schema 和内容 hash。
