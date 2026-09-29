# money-trees

Money Trees 是面向 A 股经典 Alpha 因子计算、验证和研究证据生产的工具，覆盖 Alpha101、Alpha191、Alpha158 和 Alpha360 共 810 个经典因子。完整组合、风险、执行模拟和正式回测任务分别由 `quant-platform` 与 `quant-backtest-runtime` 承担。Python import 包名是 `moneytree`，新文档优先使用 `moneytrees*` CLI（旧的 `moneytree*` 别名保留兼容）。

## 为什么叫 money-trees

名字是一个双关：

- 树模型，而且不止一棵。项目训练的主力是决策树家族：随机森林、Extra Trees、梯度提升（GradientBoosting）、HistGradientBoosting、XGBoost 分类、XGBoost 回归和 XGBoost ranking 共 7 个树模型，另配 Ridge、Lasso、ElasticNet 三个线性模型作为基准对照。复数 `trees` 直接对应一群树。
- 810 棵摇钱树。内置 Alpha101、Alpha191、Alpha158、Alpha360 四个经典因子家族共 810 个因子，每个因子都是一棵独立的树，覆盖价格、量、成交额、换手和市值等维度。
- 摇钱树（Money Tree）。在中文语境里，摇钱树象征可持续带来收益的策略。A 股量化的目标正是种下一片能长期摇出收益的因子和模型树林，单一模型或单一因子做不到这一点。

`money-trees` 是发行名和文档名，Python import 包名保留单数 `moneytree`，CLI 同时提供 `moneytrees*` 与旧 `moneytree*` 两套别名。

## 快速开始

环境要求：Python `>=3.10` 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --dev
```

跑一个最小回测：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data data_small.parquet \
  --output-dir artifacts/smoke
```

## 三条研究路径

1. 标准面板回测：准备好 `date, ticker` 面板，直接跑模型和组合回测。
2. 本地因子：从 `quant-market-data-platform` 读取已发布基础面板，用 `moneytrees-factor-store` 本地生成 Alpha158/360。旧的 `moneytrees-tushare` 仅作为兼容入口保留。
3. 完整 810 因子：在路径 2 基础上补齐 Alpha101/191，可以用纯 Python 本地生成（`moneytrees-alpha101-191-python`），也可以用 DolphinDB 外部生成（`moneytrees-dolphindb-alphas`），统一写入因子仓库（factor store）后回测。

大规模研究推荐使用因子仓库，避免长期维护单个超宽 parquet。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `moneytrees` | 按配置运行回测。 |
| `moneytrees-tushare` | **deprecated 兼容入口**：拉取 TuShare 日频数据；新研究应读取 `quant-market-data-platform` 发布资产。 |
| `moneytrees-factor-store` | 本地生成 Alpha158/360 因子仓库。 |
| `moneytrees-alpha101-191-python` | 纯 Python 本地生成 Alpha101/191（横截面语义）。 |
| `moneytrees-dolphindb-alphas` | 用 DolphinDB 外部生成 Alpha101/191。 |
| `moneytrees-factor-mining` | 用遗传算法在已有因子上挖掘新因子。 |
| `moneytrees-data-status` | 只读检查数据、因子仓库和回测产物状态。 |
| `moneytrees-parquet-rewrite` | 重写 parquet 或迁移可信 pickle。 |
| `moneytree-factor-evidence` / `moneytrees-factor-evidence` | 生成聚合的公开 Alpha 因子证据快照。 |

运行测试和 lint：

```bash
uv run pytest -q
uv run ruff check .
```

完整命令和参数见 [docs/cli-reference.md](docs/cli-reference.md)。

## 支持的模型

模型层在 `src/moneytree/models/registry.py` 注册了 10 个适配器，统一由回测 CLI 按配置调用：

- 树模型：随机森林、Extra Trees、梯度提升、HistGradientBoosting、XGBoost 分类、XGBoost 回归和 XGBoost ranking。
- 线性基准：Ridge、Lasso、ElasticNet。

分类模型训练三分类方向标签 `rel_performance`，线性模型和 XGBoost 回归训练连续目标 `rel_return`，XGBoost ranking 使用 pairwise ranking。XGBoost 相关适配器是可选依赖，缺省安装时会在调用处给出明确报错。

## 文档导航

数据接入、缓存、质量治理、版本和发布由 [`quant-market-data-platform`](https://github.com/runchengxie/quant-market-data-platform) 负责；Money Trees 的迁移边界见 [docs/data-platform-migration.md](docs/data-platform-migration.md)。

本 README 是仓库入口；[GitHub Pages 文档首页](https://runchengxie.github.io/money-trees/) 对应 [docs/index.md](docs/index.md)，由 MkDocs 构建。公开因子证据的契约见 [docs/public-factor-evidence.md](docs/public-factor-evidence.md)，发布安全边界见 [docs/publication-audit.md](docs/publication-audit.md)。研究方法见 [docs/research-methodology.md](docs/research-methodology.md)。

- [docs/index.md](docs/index.md): MkDocs 首页和项目边界入口。
- [docs/smoke-test.md](docs/smoke-test.md): 冒烟测试、最小跑通路径和最小数据列。
- [docs/architecture.md](docs/architecture.md): 数据层、市场层、因子层、模型层、组合层、回测层和输出层设计。
- [docs/data-contract.md](docs/data-contract.md): 标准面板索引、必需列、可选列、标签和特征口径。
- [docs/data-status.md](docs/data-status.md): 原始缓存、基础面板、因子仓库和回测产物的只读状态检查。
- [docs/data-snapshot.md](docs/data-snapshot.md): 基础面板、原始缓存和因子仓库的轻量元数据快照与校验码。
- [docs/data-release.md](docs/data-release.md): 面板、原始缓存和因子仓库的 GitHub Releases 发布资产生成与上传。
- [docs/configuration.md](docs/configuration.md): 配置文件分层、合并规则和常用字段。
- [docs/cli-reference.md](docs/cli-reference.md): `moneytrees*` CLI、兼容别名和高风险参数索引。
- [docs/outputs.md](docs/outputs.md): 回测产物、指标 JSON 和 run config 说明。
- [docs/cookbook.md](docs/cookbook.md): 常见研究任务示例。
- [docs/runbook.md](docs/runbook.md): 日常运行、缓存刷新、排障和归档检查。
- [docs/testing.md](docs/testing.md): 测试命令、测试覆盖和当前测试缺口。
- [docs/factor-families.md](docs/factor-families.md): Alpha101/191/158/360 因子家族来源、用途和项目边界。
- [docs/factor-catalog.md](docs/factor-catalog.md): 因子列级清单说明，机器可读版本在 [docs/factor-catalog.csv](docs/factor-catalog.csv)。
- [docs/classic-alphas-python.md](docs/classic-alphas-python.md): 用纯 Python 生成 Alpha101/191 的引擎和 CLI。
- [docs/generate-alpha101-191-with-dolphindb.md](docs/generate-alpha101-191-with-dolphindb.md): 使用 DolphinDB 生成 Alpha101/191 并写入因子仓库。
- [docs/factor-mining.md](docs/factor-mining.md): 遗传算法因子挖掘 CLI。
- [docs/maintenance.md](docs/maintenance.md): 维护待办、迁移工具和后续重构候选项。

## 项目结构

```text
configs/         回测、市场、模型和预设配置
docs/            使用、架构、数据契约和运维文档
project_tools/   仓库维护脚本
scripts/         兼容入口和迁移脚本
src/moneytree/   核心包、CLI、数据层、模型、组合和回测逻辑
tests/           单元测试、CLI 冒烟测试和数据源测试
```

## 相关项目

[guan-random-forest-cross-sectional](https://github.com/runchengxie/guan-random-forest-cross-sectional) 是本项目思路的美股姊妹版。它用随机森林做截面选股，使用 SPY 作为基准，回测框架与本项目一致，两边可以互为参考。

## 当前边界

- 市场层只有 `cn` 市场配置档，默认基准是 `000300.SH`，可交易过滤和基准净值口径见 [docs/data-contract.md](docs/data-contract.md)。
- 输入支持 parquet 和可信 pickle，推荐统一为 `date, ticker` parquet。
- Alpha101/191 有纯 Python 本地和 DolphinDB 外部两条生成路径，口径可能不同，正式研究前请先对拍（见 [docs/classic-alphas-python.md](docs/classic-alphas-python.md)）。
- DolphinDB、TuShare、XGBoost 和 Optuna 都是可选依赖。普通回测只需要已有标准面板。
- TuShare 派生标记存在上游数据治理边界（历史 ST、历史行业、退市样本和幸存者偏差），详见 [docs/data-contract.md](docs/data-contract.md)。
