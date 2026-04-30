# money-trees

Money Trees 是面向 A 股截面选股研究的经典 Alpha 因子、训练、回测和结果归档工具。项目围绕 Alpha101、Alpha191、Alpha158 和 Alpha360 共 810 个经典因子的标准列规范展开：Alpha158/360 共 518 个特征在本地生成，Alpha101/191 共 292 个特征由 DolphinDB 等外部生产器离线生成后写入因子仓库（factor store）或兼容并入标准 `date, ticker` 面板。

核心链路包括 TuShare 日频数据拉取、原始缓存、因子仓库、特征滞后、模型适配器、组合构建、滚动回测、留出验证和可复现产物输出。Python import 包名仍然是 `moneytree`。新文档优先使用 `moneytrees*` CLI；旧的 `moneytree*` CLI alias 保留为兼容入口，并与对应 `moneytrees*` 命令指向同一实现。

## 使用路径

1. 标准面板回测：使用已有 `date, ticker` 面板运行模型和组合回测。
2. 本地 518 因子：通过 TuShare 生成基础面板，再用 `moneytrees-factor-store` 生成 Alpha158/360。
3. 完整 810 因子：本地生成 Alpha158/360，用 DolphinDB 离线生成 Alpha101/191，统一写入因子仓库后回测。

大规模研究推荐使用因子仓库，避免长期维护单个超宽 parquet。

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

拉取 TuShare 基础面板：

```bash
uv sync --dev --extra research

uv run moneytrees-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/panel/cn/cn_daily_raw.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --benchmark 000300.SH
```

生成本地 Alpha158/360 因子仓库：

```bash
uv run moneytrees-factor-store \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output-dir data/factor_store/cn_daily \
  --factor-family alpha158 \
  --factor-family alpha360 \
  --chunk-trade-dates 60 \
  --progress
```

追加外部 Alpha101/191：

注意：当前 `moneytrees-dolphindb-alphas` 会在分片计算前一次性读取并上传完整输入面板。`--no-wide-output` 和 `--chunk-trade-dates` 能降低下载和落盘压力，但不能降低这个初始输入内存峰值；多年全市场面板在 8GB 级机器上可能触发 OOM。正式全量生成前先用小样本冒烟测试，或使用更大内存环境，直到输入侧分片上传实现后再在小内存机器上直接全量运行。

```bash
uv sync --dev --extra external-alphas

uv run moneytrees-dolphindb-alphas \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn_daily \
  --no-wide-output \
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

从完整因子仓库运行 XGBoost 回归：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/factor_store/cn_daily/manifest.json \
  --output-dir artifacts/xgb-alpha-all
```

DolphinDB 容器和模块路径见 [docs/generate_alpha101_191_with_dolphindb.md](docs/generate_alpha101_191_with_dolphindb.md)，本仓库也提供 `docker-compose.alpha.yml` 作为本地联调入口。

## 常用命令

运行全部测试：

```bash
uv run pytest -q
```

运行 lint：

```bash
uv run ruff check .
```

运行 CLI 冒烟测试：

```bash
uv run pytest -q tests/test_smoke.py tests/test_backtest_cli.py
```

检查数据状态：

```bash
uv run moneytrees-data-status \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn_daily/manifest.json \
  --artifacts artifacts/xgb-alpha-all
```

生成数据快照：

```bash
uv run moneytrees-data-snapshot \
  --panel data/panel/cn/cn_daily_raw.parquet \
  --raw-cache data/raw/tushare \
  --factor-store data/factor_store/cn_daily \
  --output-dir data/snapshots/cn_daily_raw \
  --label cn_daily_raw
```

重写 parquet 或迁移可信 pickle：

```bash
uv run moneytrees-parquet-rewrite \
  --input data/old.pkl \
  --output data/old.parquet
```

pickle 只能读取可信文件；正常研究路径推荐 parquet。

## 文档导航

- [docs/smoke_test.md](docs/smoke_test.md): 冒烟测试、最小跑通路径和最小数据列。
- [docs/architecture.md](docs/architecture.md): 数据层、市场层、因子层、模型层、组合层、回测层和输出层设计。
- [docs/data_contract.md](docs/data_contract.md): 标准面板索引、必需列、可选列、标签和特征口径。
- [docs/data_status.md](docs/data_status.md): 原始缓存、基础面板、因子仓库和回测产物的只读状态检查。
- [docs/data_snapshot.md](docs/data_snapshot.md): 基础面板、原始缓存和因子仓库的轻量元数据快照与校验码。
- [docs/configuration.md](docs/configuration.md): 配置文件分层、合并规则和常用字段。
- [docs/outputs.md](docs/outputs.md): `metrics.json`、`run_config.json`、CSV 和留出验证产物说明。
- [docs/cookbook.md](docs/cookbook.md): 常见研究任务示例。
- [docs/runbook.md](docs/runbook.md): 日常运行、缓存刷新、排障和归档检查。
- [docs/testing.md](docs/testing.md): 测试命令、测试覆盖和当前测试缺口。
- [docs/factor_families.md](docs/factor_families.md): Alpha101/191/158/360 因子家族来源、用途和项目边界。
- [docs/factor_catalog.md](docs/factor_catalog.md): 因子列级清单说明，机器可读版本在 [docs/factor_catalog.csv](docs/factor_catalog.csv)。
- [docs/generate_alpha101_191_with_dolphindb.md](docs/generate_alpha101_191_with_dolphindb.md): 使用 DolphinDB 生成 Alpha101/191 并写入因子仓库。
- [docs/maintenance.md](docs/maintenance.md): 维护 backlog、迁移工具和后续重构候选项。

## 项目结构

```text
configs/
  backtest/   回测窗口、成本、留出验证和输出配置
  market/     A 股市场配置档
  model/      内置模型入口配置
  preset/     可叠加的本地运行预设配置
docs/         使用、架构、数据契约和运维文档
project_tools/ 仓库维护脚本
scripts/      兼容入口和迁移脚本
src/moneytree/ 核心包、CLI、数据层、模型、组合和回测逻辑
tests/        单元测试、CLI 冒烟测试和数据源测试
```

## 当前边界

- 市场层只有 `cn` 市场配置档，默认基准是 `000300.SH`。
- 输入数据支持 pickle 和 parquet，推荐统一为 `date, ticker` MultiIndex parquet。
- `benchmark_cum_ret` 默认按净值/指数口径处理，配置字段是 `market.benchmark_cum_mode: nav`。
- 缺失特征列默认报错；旧 notebook 复现可通过 `features.missing_feature_policy: warn_fill_zero` 迁移。
- TuShare `stock_basic.name` 推导的 `is_st` 是最新名称标记，历史 ST、历史行业归属、退市股票完整样本和幸存者偏差需要在上游数据治理中解决。
- Alpha158/360 是本地生成的日频特征；Alpha101/191 是外部生成后写入因子仓库或兼容并入标准面板的列规范。
- DolphinDB、TuShare、XGBoost 和 Optuna 都是可选依赖；普通回测只需要已有标准面板。
- 当前数据保存路线是原始 parquet 缓存、`manifest.sqlite`、可重建标准面板、因子仓库和回测产物；回测会生成 `experiment_manifest.json`。
