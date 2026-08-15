# 测试说明

项目测试覆盖数据契约、配置解析、模型适配器、组合权重、回测指标、CLI 冒烟路径、TuShare 标准化、因子仓库、数据状态、数据快照、数据发布资产、外部 Alpha 生产、容器运行文件、维护脚本和文档清单。

## 命令

完整测试：

```bash
uv run pytest -q
```

运行 lint：

```bash
uv run ruff check .
```

只跑 CLI 冒烟测试：

```bash
uv run pytest -q tests/test_smoke.py tests/test_backtest_cli.py
```

只跑 TuShare 数据源测试：

```bash
uv run pytest -q tests/test_tushare_data_source.py
```

只跑 DolphinDB 外部 Alpha mocked 测试：

```bash
uv run pytest -q tests/test_build_dolphindb_alphas_script.py tests/test_external_alphas.py
```

只跑经典 Alpha101/191 本地生成和因子挖掘：

```bash
uv run pytest -q tests/test_classic_alphas.py tests/test_mining.py
```

只跑组合和回测核心：

```bash
uv run pytest -q tests/test_portfolio.py tests/test_backtest.py
```

只跑工程化 CLI 测试：

```bash
uv run pytest -q tests/test_data_status.py tests/test_data_snapshot.py tests/test_data_release.py tests/test_factor_store.py tests/test_parquet_rewrite_cli.py
```

只跑文档 guard 测试：

```bash
uv run pytest -q tests/test_docs_inventory.py tests/test_docs_console_scripts.py tests/test_docs_links.py tests/test_docs_style.py
```

文档 guard 测试覆盖测试文件登记、console script 名称、README 文档导航、内部 Markdown 链接、部分文风规则、核心术语反向检查、CLI 高风险参数覆盖和因子目录状态一致性。它们不会逐条执行 README 或 docs 中的完整命令示例。涉及 TuShare token、DolphinDB server、大型数据文件或长时间运行的命令仍需按运行手册单独验证。

## 当前覆盖

| 文件 | 覆盖重点 |
| --- | --- |
| `tests/test_backtest.py` | 滚动窗口、绩效指标、基准净值口径、缺失特征策略、组合诊断、Notebook 报告数据和样本外结果序列。 |
| `tests/test_backtest_cli.py` | CLI 配置栈、`--set` 覆盖、默认配置、留出验证、输出文件、run config 元数据和错误参数。 |
| `tests/test_build_dolphindb_alphas_script.py` | DolphinDB Alpha101/191 CLI、兼容入口、元数据清单脱敏和可选依赖报错。 |
| `tests/test_classic_alphas.py` | 纯 Python Alpha101/191 本地生成：列契约、横截面 rank 语义、CLI 宽面板和因子仓库输出。 |
| `tests/test_container_runtime.py` | Dockerfile、`.dockerignore`、DolphinDB compose 和 runtime 输出隔离。 |
| `tests/test_convert_pickle_to_parquet_script.py` | 可信 pickle 到 parquet 的 deprecated 兼容迁移脚本和迁移提示。 |
| `tests/test_data.py` | `date,ticker` 索引、标签生成、特征缺失填充、非特征列保护、特征滞后和文件格式错误。 |
| `tests/test_data_release.py` | 数据发布资产、本地分片、不压缩 tar、GitHub CLI 命令预览和敏感文件保护。 |
| `tests/test_data_snapshot.py` | 数据快照 metadata、checksum、README、质量摘要和 CLI 错误路径。 |
| `tests/test_data_status.py` | 面板、原始缓存、因子仓库、回测产物的只读检查、JSON 输出和 error/warn 模式。 |
| `tests/test_docs_console_scripts.py` | `pyproject.toml` 中 console scripts、兼容别名和 CLI 高风险参数在 README 或 docs 中的覆盖。 |
| `tests/test_docs_inventory.py` | `tests/test_*.py` 文件是否全部登记在本文档。 |
| `tests/test_docs_links.py` | README 和 docs 内部 Markdown 链接是否存在，README 文档导航是否覆盖所有用户文档。 |
| `tests/test_docs_style.py` | 中文文档中高风险间接句式、核心术语漂移、DolphinDB 模块事实和因子目录状态一致性。 |
| `tests/test_export_repo_source.py` | 源码导出工具是否包含配置和因子清单，同时继续排除运行数据目录。 |
| `tests/test_external_alphas.py` | 外部 Alpha101/191 列名、字段映射、输入依赖、并入和元数据清单校验。 |
| `tests/test_factor_store.py` | 本地因子仓库、外部因子仓库、元数据清单、分区、压缩、覆盖和选择加载。 |
| `tests/test_factors.py` | Alpha158/360 列数、本地因子追加、因子 IC、因子目录元数据和 internal factor ops 状态。 |
| `tests/test_model.py` | 随机森林调参、时间序列 CV、特征选择、Optuna 可选依赖和 legacy notebook 兼容路径。 |
| `tests/test_mining.py` | GP 因子挖掘：终端解析、表达式工具、适应度、报告输出和 CLI 冒烟。 |
| `tests/test_moneytree_registry.py` | 模型注册表、市场注册表、`cn` 基准列映射和可交易过滤。 |
| `tests/test_package_script.py` | `project_tools/package.sh` 输出目录、运行数据包含策略、source-only 模式和压缩格式。 |
| `tests/test_parquet_rewrite_cli.py` | parquet/pickle 重写、压缩、row group 和禁止原地覆盖。 |
| `tests/test_portfolio.py` | 信号分数、启发式权重、暴露约束、波动率缩放、行业中性、QP 权重、换手惩罚和 fallback 诊断。 |
| `tests/test_project_identity.py` | Money Trees distribution identity、`moneytree` import 兼容和 CLI alias。 |
| `tests/test_resources.py` | 内存预检、parquet 加载估算和字节格式化。 |
| `tests/test_smoke.py` | 冒烟测试配置栈端到端运行。 |
| `tests/test_tushare_data_source.py` | TuShare 标准化、token、原始缓存、`manifest.sqlite` 元数据、旧元数据清单迁移、近期刷新和最新名称 ST 标记。 |

## 可选依赖

默认开发依赖本身不要求 XGBoost、TuShare 或 DolphinDB：

```bash
uv sync --dev
```

XGBoost 相关测试会验证缺依赖时报错清晰。如果当前环境已经安装 `xgboost`，缺依赖断言会跳过。需要真实运行 XGBoost 模型时：

```bash
uv sync --dev --extra xgboost
```

TuShare CLI 真实拉取需要：

```bash
uv sync --dev --extra tushare
```

DolphinDB 外部 Alpha101/191 生成需要：

```bash
uv sync --dev --extra external-alphas
```

Optuna 调参运行需要：

```bash
uv sync --dev --extra tuning
```

## 当前测试缺口

- 文档命令执行检查：README 和 docs 中出现的完整 CLI 示例目前只做存在性、链接和关键参数覆盖保护，尚未逐条运行。
- 输出文件 hash 检查：`experiment_manifest.json` 已记录输入和配置 hash，后续可继续记录每个 CSV/JSON 产物 hash。
- 更真实的 A 股执行模型：当前组合测试覆盖权重、暴露和换手，尚未覆盖涨跌停无法成交、成交量容量和冲击成本。
- 历史 point-in-time ST 和行业归属：当前测试只保证最新名称 ST 标记被明确标注语义。
