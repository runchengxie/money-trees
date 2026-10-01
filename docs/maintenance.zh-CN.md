# 维护待办

[English page](maintenance.md)

本文记录当前暂不强行重构、但后续值得拆分和治理的模块边界。它不是主运行手册。实施较大重构前，应先补充或更新对应的设计说明或实施方案。

## 大文件和职责边界

表中源码行数核对于 2026-10-01。待办聚焦职责混合、测试面广、后续修改频繁的核心模块，不代表必须整体重写。

| 文件 | 行数（2026-10-01） | 当前问题 | 后续建议 |
| --- | ---: | --- | --- |
| `src/moneytree/factor_store.py` | 2020 | local/external 因子仓库、分区、压缩、schema 校验和加载逻辑仍集中。元数据清单和 validation 已部分拆分到独立模块。 | 继续拆 partitioning、local writer、external writer 和 IO helpers，保留 `moneytree.factor_store` facade。 |
| `src/moneytree/runner.py` | 878 | 回测 orchestration 仍集中；输出、留出验证和 summary 已部分拆到独立模块。 | 继续拆解 orchestration，保持 `run_backtest()` 入口不变。 |
| `src/moneytree/data_sources/tushare.py` | 1069 | TuShare client、原始缓存、标准化和元数据清单迁移集中。 | 拆出 client、cache、standardize、元数据清单 migration。 |
| `src/moneytree/data.py` | 880 | 数据读取、索引归一、标签生成、特征筛选和缺失策略集中。 | 后续按 loading、labels、feature policy、index helpers 分层。 |
| `src/moneytree/cli/dolphindb_alphas.py` | 826 | CLI 参数、DolphinDB 调度、streaming、输出校验和元数据清单混合。 | 后续拆出 argument validation、streaming generation、output validation。 |
| `src/moneytree/data_status.py` | 822 | 面板、原始缓存、因子仓库和回测产物的状态检查与展示混合。 | 后续拆出 layer inspectors、quality checks、renderers。 |
| `src/moneytree/backtest.py` | 688 | 滚动窗口、指标、诊断和序列拼接混在一起。 | 拆出 metrics、rolling、diagnostics，保持公开函数 re-export。 |
| `src/moneytree/portfolio.py` | 657 | 启发式权重、QP、协方差估计和约束逻辑集中。 | 拆成 portfolio config、heuristic、QP、risk/covariance helpers。 |
| `src/moneytree/model.py` | 707 | 随机森林工具、评分、调参、特征选择和 legacy notebook 路径混在一起。 | 拆出 scoring、model selection、random forest tuning、legacy compatibility。 |
| `src/moneytree/factors/external.py` | 424 | 外部 Alpha 字段映射、校验、merge 和元数据清单逻辑集中。 | 后续可拆出 field mapping、validation、元数据清单 helpers。 |

## 历史和兼容工具

生命周期状态：

- `active`: 正式路径，文档和新示例可以继续使用。
- `compatibility`: 兼容路径，保持可用，但新文档不优先推荐。
- `deprecated`: 已有替代路径，继续可用一段时间，并给出迁移提示。
- `removal-candidate`: 仅在确认没有测试、文档或外部兼容承诺后删除。

| 项 | 状态 | 证据 | 推荐路径 |
| --- | --- | --- | --- |
| `scripts/convert_pickle_to_parquet.py` | `deprecated` | 仅覆盖可信 pickle 到 parquet 迁移。主数据契约已推荐 `moneytrees-parquet-rewrite`。 | 使用 `uv run moneytrees-parquet-rewrite --input old.pkl --output old.parquet`。 |
| `scripts/build_dolphindb_alphas.py` | `compatibility` | 测试确认它只代理 `moneytree.cli.dolphindb_alphas`。外部脚本可能仍引用旧路径。 | 新命令使用 `moneytrees-dolphindb-alphas`。 |
| `configs/preset/notebook_compat.yaml` | `deprecated` | 与 `legacy_notebook_compat.yaml` 内容一致，但语义是过渡兼容路径。 | 使用 `configs/preset/legacy_notebook_compat.yaml` 复现早期 notebook。 |
| `configs/preset/legacy_notebook_compat.yaml` | `compatibility` | 明确用于复现早期 notebook，不是默认研究路径。 | 正式研究优先使用基础市场配置档和模型配置。 |
| `moneytree*` 单数 CLI alias | `compatibility` | `pyproject.toml` 和测试保留 alias，避免破坏旧命令。 | 新文档优先使用 `moneytrees*`。 |
| pickle 输入支持 | `compatibility` | 数据契约允许读取可信旧数据，但 parquet 是推荐格式。 | 迁移为 parquet 或因子仓库输入。 |
| legacy notebook model path | `compatibility` | `notebook_compat` 特征选择和调参路径仍有测试覆盖。 | 新实验使用默认 feature lag、默认缺失策略和正式配置栈。 |
| `moneytree.factors.ops` | `compatibility` | 作为 `moneytree.factors.ops` 子模块有测试覆盖，但未从 `moneytree.factors` 顶层导出。 | 继续作为 internal operator helper。顶层 API 使用 `moneytree.factors` 已导出的因子族和 IC 函数。 |

## 建议拆分顺序

1. `runner.py`: 继续拆分 orchestration stages，保持 `run_backtest()` 入口稳定。
2. `factor_store.py`: 在元数据清单和 validation helpers 已拆出的基础上，继续拆分 partitioning、writers 和 loading。
3. `backtest.py`: 拆 metrics、rolling 和 diagnostics，保持公开函数 re-export。
4. `portfolio.py`: 拆 heuristic、QP、risk/covariance 和 diagnostics。
5. `model.py`: 收口 legacy random forest free functions 到兼容 facade。
6. `data_sources/tushare.py`: 拆 client、cache、fetch、standardize 和面板组装。

截至 2026-10-01，runner 的输出、留出验证、summary，以及因子仓库元数据清单和 validation 已由独立模块承接。因子仓库 writer、loader、partitioning 仍是后续拆分对象，拆分时继续保持 `moneytree.factor_store` facade。

## 质量门槛

日常开发至少运行：

```bash
uv run ruff check .
uv run pytest -q
```

涉及 TuShare、DolphinDB、模型适配器、配置解析、输出文件或数据契约时，应补充对应专项测试。

Ruff 当前执行 `E/F/I/UP/B`，`line-length = 100` 但暂时忽略 `E501`。本轮治理只在触及模块内整理明显长行和密集表达，避免把全仓库机械换行混入架构调整。候选规则分阶段处理：

| 规则 | 状态 | 说明 |
| --- | --- | --- |
| `C90` | 待办 | 用于发现过高圈复杂度，先审计 `runner.py`、`factor_store.py`、`portfolio.py`。 |
| `SIM` | 待办 | 简化分支和表达式，适合在模块拆分后逐步启用。 |
| `RET` | 待办 | 清理 return 风格，先不全仓库开启。 |
| `ARG` | 待办 | 检查未使用参数，需谨慎处理 CLI callback、测试 fixture 和兼容 facade。 |
| `E501` | scoped | 继续全局忽略。触及代码按 100 字符意图主动整理。 |
