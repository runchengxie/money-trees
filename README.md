# money-tree

`money-tree` 是一个面向 A 股截面选股研究的训练、回测和结果归档工具。当前内置市场只覆盖 `cn`，主链路包括 TuShare 日频数据拉取、标准 `date, ticker` 面板、Alpha158/360 本地特征、模型适配器、组合构建、滚动回测、holdout 验证和报告产物输出。

## 快速开始

环境要求：

- Python `>=3.10`
- `uv`

安装开发依赖：

```bash
uv sync --dev
```

默认运行会叠加这三个配置文件：

- `configs/market/cn.yaml`
- `configs/model/rf.yaml`
- `configs/backtest/default.yaml`

运行回测：

```bash
uv run moneytree \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

显式传配置文件时，后面的文件会覆盖前面的同名字段：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

局部覆盖配置：

```bash
uv run moneytree \
  --data data_small.parquet \
  --output-dir artifacts/backtest \
  --set backtest.segment1_windows=1 \
  --set backtest.segment2_windows=1
```

拉取 TuShare 日频数据并追加本地 Alpha 特征：

```bash
uv sync --dev --extra research

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

使用 XGBoost 回归模型跑日频 Alpha 回测：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha.parquet \
  --output-dir artifacts/xgb-alpha-daily
```

## 常用命令

```bash
uv run pytest -q
```

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data data_small.parquet \
  --output-dir artifacts/smoke
```

```bash
uv run python scripts/convert_pickle_to_parquet.py \
  --input data_small.pkl
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

## 项目结构

```text
configs/
  backtest/   回测窗口、成本、holdout 和输出配置
  market/     A 股市场配置
  model/      内置模型入口配置
  preset/     可叠加的本地运行预设
docs/         使用、架构、数据契约和运维文档
project_tools/ 仓库维护脚本
scripts/      数据转换脚本
src/moneytree/ 核心包、CLI、数据层、模型、组合和回测逻辑
tests/        单元测试、CLI 冒烟测试和数据源测试
```

## 当前边界

- 市场层只有 `cn` 配置档，默认基准是 `000300.SH`。
- 输入数据支持 pickle 和 parquet，推荐统一为 `date, ticker` MultiIndex parquet。
- TuShare 支持依赖 `research` 或 `tushare` extra，token 通过显式参数、环境变量或 `.env` 读取。
- XGBoost 分类和回归模型依赖 `xgboost` extra。
- A 股历史 ST、历史行业归属、退市股票完整样本和幸存者偏差需要在上游数据治理中解决。
- 当前数据保存路线是 raw parquet cache + `manifest.sqlite` + 可重建标准面板 + 回测产物；回测会生成 `experiment_manifest.json`，TuShare cache manifest 会记录请求、schema 和内容 hash。更重的存储技术栈等数据规模和协作压力上来后再评估。
