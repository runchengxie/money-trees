## Why

项目经过多轮功能扩张后，核心能力已经覆盖 A 股 `date, ticker` 面板、TuShare 原始缓存、factor store、DolphinDB 外部 Alpha101/191、模型适配器、组合构建、滚动回测、留出验证和可复现产物。当前主要风险集中在三类维护债：若干大模块职责过重，部分研究口径存在影响回测可信度的细节风险，README、AGENTS 和 docs/testing.md 等入口文档没有完整反映后期新增的 CLI、测试和运行事实。

这次变更把项目清债拆成可验证的工程工作，目标是先修正会影响研究结论的逻辑风险，再同步文档和测试说明，最后为大文件拆分、兼容入口下线和 lint 门槛提升建立明确路线。

## What Changes

- 收敛回测正确性风险：
  - 限制 `preprocess_data()` 的前向填充范围，避免收益、标签、可交易状态、ST、停牌和涨跌停字段被跨日期填补。
  - 明确 `benchmark_cum_ret` 口径，并让 `build_benchmark_nav()` 支持净值/指数和累计收益两类输入。
  - 让收益指标优先从 `strategy_returns` / `benchmark_returns` 复利计算完整区间收益，避免 NAV 序列缺初始点时漏算首期。
  - 将缺失特征列默认处理策略从静默补 0 收紧为可配置策略，默认失败并给出明确错误。
  - 对 TuShare `stock_basic.name` 推导出的 `is_st` 增加 point-in-time 风险提示或字段重命名，避免用户误认为它是历史 ST 状态。
- 更新项目入口文档：
  - README 增补 `moneytrees-data-status`、`moneytrees-data-snapshot`、`moneytrees-factor-store`、`moneytrees-parquet-rewrite`、DolphinDB 容器路径和 pickle 安全说明。
  - AGENTS.md 同步新增 CLI、测试命令、重要路径和当前数据安全规则。
  - docs/testing.md 补齐当前测试文件清单和专项测试命令。
  - docs/data_snapshot.md 中文化并补充 `--note` 示例。
  - docs/architecture.md、docs/maintenance.md 将 factor store 作为一等模块和重点维护对象。
- 建立文档与测试一致性保护：
  - 新增文档清单测试，检查 `tests/test_*.py` 是否在 docs/testing.md 中登记。
  - 新增 console script 文档覆盖测试，检查 `pyproject.toml` 中的 CLI 是否至少出现在 README 或 docs 中。
  - 新增 Markdown 内部链接测试和轻量中文风格检查。
- 规划低风险清理：
  - 标记 `scripts/build_dolphindb_alphas.py`、`scripts/convert_pickle_to_parquet.py` 和 `configs/preset/notebook_compat.yaml` 的历史兼容定位。
  - 为 `moneytree` / `moneytrees` 双 CLI alias 写明兼容生命周期。
  - 移除 README 中的歌词引用，改为原创项目描述。
- 分阶段提升代码质量门槛：
  - 先扩展 Ruff 到导入排序、pyupgrade 和 bugbear 等低风险规则。
  - 将 `factor_store.py`、`runner.py`、`backtest.py`、`portfolio.py`、`data_sources/tushare.py` 的拆分列入后续可测试任务，保留当前公开入口。

## Capabilities

### New Capabilities
- `project-maintenance-governance`: 维护项目事实、文档清单、历史兼容入口和代码质量门槛的治理规则。
- `research-backtest-correctness`: 保护数据预处理、基准净值、收益指标、缺失特征和 A 股状态字段的回测正确性规则。

### Modified Capabilities

## Impact

- 代码影响：
  - `src/moneytree/data.py`
  - `src/moneytree/backtest.py`
  - `src/moneytree/runner.py`
  - `src/moneytree/data_sources/tushare.py`
  - `src/moneytree/config.py`
  - `configs/market/cn.yaml`
  - `configs/backtest/*.yaml`
  - `pyproject.toml`
- 文档影响：
  - `README.md`
  - `AGENTS.md`
  - `docs/testing.md`
  - `docs/data_snapshot.md`
  - `docs/architecture.md`
  - `docs/maintenance.md`
  - `docs/data_contract.md`
  - `docs/runbook.md`
  - `docs/cookbook.md`
- 测试影响：
  - 新增回测正确性单元测试。
  - 新增文档库存、CLI 覆盖、内部链接和语言风格测试。
  - 更新现有数据、回测、TuShare、CLI 和项目身份测试。
- 兼容性影响：
  - 默认缺失特征处理会从静默补 0 变为失败；需要保留迁移期配置以支持旧 notebook 和旧数据。
  - `benchmark_cum_ret` 需要在市场配置档中声明口径，旧配置可通过默认值兼容。
  - pickle 输入继续可用，但文档和运行提示会明确只读取可信文件。
