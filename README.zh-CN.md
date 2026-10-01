# Money Trees · Alpha 810 Research

[English page](README.md)

Money Trees 是面向 A 股经典 Alpha 因子计算、验证和研究证据生产的工具，覆盖 Alpha101、Alpha191、Alpha158 和 Alpha360，共 810 个因子。项目提供因子生成入口、列级目录、因子仓库和基础评估。完整组合构建、风险分析、执行模拟和回测任务由 `quant-platform` 与 `quant-backtest-runtime` 负责。

发行包和文档名称为 `money-trees`，Python import 包名保留为 `moneytree`。新工作流优先使用 `moneytrees*` 命令，旧的 `moneytree*` 别名继续兼容。

## 快速开始

环境要求：Python `>=3.10` 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --dev
```

使用本地面板运行最小回测：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data data_small.parquet \
  --output-dir artifacts/smoke
```

标准面板使用 `date, ticker`。优先使用 Parquet；pickle 仅支持可信的历史数据。

## 研究路径

1. 准备 `date, ticker` 数据集，运行标准面板回测。
2. 从 `quant-market-data-platform` 读取已发布基础面板，用 `moneytrees-factor-store` 在本地生成 Alpha158/360。`moneytrees-tushare` 是已弃用的兼容入口；新数据生产由数据平台负责。
3. 使用纯 Python 横截面引擎（`moneytrees-alpha101-191-python`）或外部 DolphinDB 流程（`moneytrees-dolphindb-alphas`）补充 Alpha101/191。两种生成方式的语义可能不同，正式研究前应先对拍结果。

大规模研究建议使用因子仓库，避免长期维护单个超宽 Parquet 文件。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `moneytrees` | 按配置运行回测。 |
| `moneytrees-tushare` | 已弃用的兼容命令，用于下载 TuShare 日频数据。优先使用 `quant-market-data-platform` 发布的资产。 |
| `moneytrees-factor-store` | 本地生成 Alpha158/360 因子仓库。 |
| `moneytrees-alpha101-191-python` | 使用纯 Python 横截面引擎生成 Alpha101/191。 |
| `moneytrees-dolphindb-alphas` | 通过外部 DolphinDB 流程生成 Alpha101/191。 |
| `moneytrees-factor-mining` | 使用遗传算法从已有因子中挖掘新因子。 |
| `moneytrees-data-status` | 只读检查数据、因子仓库和回测产物状态。 |
| `moneytrees-parquet-rewrite` | 重写 Parquet 或迁移可信的 pickle 数据。 |
| `moneytrees-factor-evidence` | 生成聚合的公开 Alpha 因子证据快照。 |

对应的 `moneytree*` 兼容别名包括 `moneytree`、`moneytree-tushare`、`moneytree-data-status`、`moneytree-data-snapshot`、`moneytree-data-release`、`moneytree-dolphindb-alphas`、`moneytree-alpha101-191-python`、`moneytree-factor-mining`、`moneytree-factor-store`、`moneytree-parquet-rewrite` 和 `moneytree-factor-evidence`。参数和高风险选项见 [CLI 参考](docs/cli-reference.zh-CN.md)。

运行测试和 lint：

```bash
uv run pytest -q
uv run ruff check .
```

## 模型适配器

模型注册表包含 10 个适配器：随机森林、Extra Trees、Gradient Boosting、HistGradientBoosting、XGBoost 分类、XGBoost 回归、XGBoost 排序、Ridge、Lasso 和 ElasticNet。分类适配器使用三分类标签 `rel_performance`。线性模型和 XGBoost 回归使用连续标签 `rel_return`；XGBoost 排序采用 pairwise ranking。XGBoost 为可选依赖，未安装对应 extra 时会给出明确错误。

## 文档

[GitHub Pages 文档](https://runchengxie.github.io/money-trees/)由 [`docs/index.zh-CN.md`](docs/index.zh-CN.md) 构建。数据接入、缓存、质量治理、版本和发布由 [`quant-market-data-platform`](https://github.com/runchengxie/quant-market-data-platform) 负责，边界说明见[数据平台迁移文档](docs/data-platform-migration.zh-CN.md)。完整组合构建、风险、执行模拟和回测任务由 `quant-platform` 与 `quant-backtest-runtime` 负责。

- [`docs/index.zh-CN.md`](docs/index.zh-CN.md)：项目边界和公开文档入口。
- [`docs/language-migration-status.zh-CN.md`](docs/language-migration-status.zh-CN.md)：中英文页面覆盖和本地化范围。
- [`docs/public-factor-evidence.zh-CN.md`](docs/public-factor-evidence.zh-CN.md)、[`docs/publication-audit.zh-CN.md`](docs/publication-audit.zh-CN.md) 和 [`docs/research-methodology.zh-CN.md`](docs/research-methodology.zh-CN.md)：证据契约、发布控制和研究方法。
- [`docs/smoke-test.zh-CN.md`](docs/smoke-test.zh-CN.md)：最小端到端运行流程和必需面板列。
- [`docs/architecture.zh-CN.md`](docs/architecture.zh-CN.md)：数据、市场、因子、模型、组合、回测和输出分层。
- [`docs/data-contract.zh-CN.md`](docs/data-contract.zh-CN.md)：面板索引、必需与可选列、标签和特征语义。
- [`docs/data-status.zh-CN.md`](docs/data-status.zh-CN.md)、[`docs/data-snapshot.zh-CN.md`](docs/data-snapshot.zh-CN.md) 和 [`docs/data-release.zh-CN.md`](docs/data-release.zh-CN.md)：只读状态、元数据快照和发布资产。
- [`docs/configuration.zh-CN.md`](docs/configuration.zh-CN.md)：配置分层、合并规则和字段。
- [`docs/cli-reference.zh-CN.md`](docs/cli-reference.zh-CN.md)：`moneytrees*` 命令、兼容别名和高风险选项。
- [`docs/outputs.zh-CN.md`](docs/outputs.zh-CN.md)、[`docs/cookbook.zh-CN.md`](docs/cookbook.zh-CN.md) 和 [`docs/runbook.zh-CN.md`](docs/runbook.zh-CN.md)：回测产物、常见研究流程、运维与排障。
- [`docs/testing.zh-CN.md`](docs/testing.zh-CN.md)：测试命令、覆盖情况和已知缺口。
- [`docs/factor-families.zh-CN.md`](docs/factor-families.zh-CN.md) 和 [`docs/factor-catalog.zh-CN.md`](docs/factor-catalog.zh-CN.md)：因子族来源和目录；机器可读目录见 [`docs/factor-catalog.csv`](docs/factor-catalog.csv)。
- [`docs/classic-alphas-python.zh-CN.md`](docs/classic-alphas-python.zh-CN.md) 和 [`docs/generate-alpha101-191-with-dolphindb.zh-CN.md`](docs/generate-alpha101-191-with-dolphindb.zh-CN.md)：Alpha101/191 的两种生成方式。
- [`docs/factor-mining.zh-CN.md`](docs/factor-mining.zh-CN.md) 和 [`docs/maintenance.zh-CN.md`](docs/maintenance.zh-CN.md)：因子挖掘和仓库维护。

## 项目结构

```text
configs/         回测、市场、模型和预设配置
docs/            使用、架构、数据契约和运维文档
project_tools/   仓库维护工具
scripts/         兼容入口和迁移脚本
src/moneytree/   核心包、CLI、数据、模型、组合和回测代码
tests/           单元测试、CLI 冒烟测试和数据源测试
```

## 相关项目

[guan-random-forest-cross-sectional](https://github.com/runchengxie/guan-random-forest-cross-sectional) 是美股姊妹项目，使用随机森林进行截面选股，并以 SPY 为基准。

## 当前边界

- 内置市场配置档为 `cn`，默认基准是 `000300.SH`。可交易过滤和基准累计收益语义见 [`docs/data-contract.zh-CN.md`](docs/data-contract.zh-CN.md)。
- 输入支持 Parquet 和可信 pickle，推荐使用 `date, ticker` Parquet。
- Alpha101/191 可通过纯 Python 本地生成或外部 DolphinDB 生成。正式研究前应核对两者语义，详见上述生成指南。
- DolphinDB、TuShare、XGBoost 和 Optuna 均为可选依赖。使用标准面板回测不要求全部安装。
- TuShare 派生标签存在上游数据治理限制，包括历史 ST 状态、历史行业、退市样本和幸存者偏差。详见 [`docs/data-contract.zh-CN.md`](docs/data-contract.zh-CN.md)。
