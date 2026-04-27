# 测试说明

项目测试覆盖数据契约、配置解析、模型适配器、组合权重、回测指标、CLI 冒烟路径、TuShare 标准化和维护脚本。

## 命令

完整测试：

```bash
uv run pytest -q
```

只跑 CLI 冒烟测试：

```bash
uv run pytest -q tests/test_smoke.py tests/test_backtest_cli.py
```

只跑 TuShare 数据源测试：

```bash
uv run pytest -q tests/test_tushare_data_source.py
```

只跑组合和回测核心：

```bash
uv run pytest -q tests/test_portfolio.py tests/test_backtest.py
```

## 当前覆盖

| 文件 | 覆盖重点 |
| --- | --- |
| `tests/test_data.py` | `date,ticker` 索引、标签生成、缺失填充、特征滞后、文件格式错误。 |
| `tests/test_moneytree_registry.py` | 模型注册表、市场注册表、`cn` 基准列映射和可交易过滤。 |
| `tests/test_model.py` | 随机森林调参、时间序列 CV、特征选择和 notebook 兼容路径。 |
| `tests/test_factors.py` | Alpha158/360 列数、本地因子追加、因子 IC、因子目录元数据。 |
| `tests/test_portfolio.py` | 信号分数、启发式权重、暴露约束、波动率缩放、行业中性、QP 权重和换手惩罚。 |
| `tests/test_backtest.py` | 滚动窗口、绩效指标、基准净值、Notebook 报告数据和样本外结果序列。 |
| `tests/test_backtest_cli.py` | CLI 配置栈、`--set` 覆盖、默认配置、holdout、输出文件和错误参数。 |
| `tests/test_smoke.py` | smoke 配置栈端到端运行。 |
| `tests/test_tushare_data_source.py` | TuShare 标准化、token、raw cache、`manifest.sqlite` 元数据、旧 manifest 迁移和近期刷新。 |
| `tests/test_convert_pickle_to_parquet_script.py` | pickle 到 parquet 转换脚本。 |
| `tests/test_export_repo_source.py` | 源码导出工具是否包含配置和因子清单，同时继续排除运行数据目录。 |

## 可选依赖

默认开发依赖本身不要求 XGBoost 和 TuShare：

```bash
uv sync --dev
```

XGBoost 相关测试会验证缺依赖时报错清晰；如果当前环境已经安装 `xgboost`，缺依赖断言会跳过。需要真实运行 XGBoost 模型时：

```bash
uv sync --dev --extra xgboost
```

TuShare CLI 真实拉取需要：

```bash
uv sync --dev --extra tushare
```

研究场景通常使用：

```bash
uv sync --dev --extra research
```

## 测试数据特点

测试内动态构造小型季度或月度面板，不依赖真实行情文件。典型列包括：

```text
date
ticker
f_signal
f_rank
next_period_return
benchmark_next_period_return
benchmark_cum_ret
is_suspended
is_st
hit_up_limit
hit_down_limit
```

TuShare 测试使用 fake client，不访问网络。

## 当前缺口

建议后续补充：

- 文档命令检查：验证 README 和 docs 中引用的关键配置路径存在。
- 输出契约测试：将 [outputs.md](outputs.md) 的文件清单与 CLI 输出断言统一维护。
- 数据契约测试：把 [data_contract.md](data_contract.md) 的最小必需列转成参数化测试。
- 导出工具测试：确认 `configs/**/*.yaml` 和 `docs/factor_catalog.csv` 会进入源码审查包。
- 输出文件 hash 测试：如果后续把每个 CSV/JSON 的 hash 写入 manifest，需要补对应断言。
