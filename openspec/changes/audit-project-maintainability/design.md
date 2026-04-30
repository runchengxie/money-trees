## Context

Money Trees 当前已经形成较完整的研究链路：TuShare 原始缓存、标准 `date, ticker` 面板、本地 Alpha158/360、外部 Alpha101/191、factor store、模型适配器、组合构建、滚动回测、留出验证、数据状态检查、数据快照和可复现产物。近期新增能力主要集中在工程化和大数据量路径，README、AGENTS.md、docs/testing.md、docs/architecture.md 和 docs/maintenance.md 仍有同步缺口。

静态检查确认了几个高优先级事实：

- `src/moneytree/factor_store.py` 约 1739 行，是当前最大模块，但 docs/maintenance.md 未列入重点拆分对象。
- `src/moneytree/runner.py` 约 1232 行，继续承担回测编排、holdout、输出写入和 summary 组装。
- `src/moneytree/data.py::preprocess_data()` 当前对整张表按 ticker 前向填充，随后才生成标签。
- `src/moneytree/backtest.py::build_benchmark_nav()` 当前用 `benchmark - first + 1` 构造基准净值。
- `run_rolling_backtest()` 输出的第一条 NAV 已经是首个测试期结束后的净值，`compute_performance_metrics()` 当前从 NAV 首尾比值计算总收益。
- 缺失特征列在 rolling 和 holdout 路径中会静默补 `0.0`。
- TuShare `stock_basic.name` 推导的 `is_st` 是当前基础信息推导结果，缺少历史 point-in-time 语义说明。
- pyproject.toml 的 Ruff 仅启用 `E`、`F` 且忽略 `E501`。
- tests 目录当前有 19 个 `test_*.py` 文件，docs/testing.md 未登记 `test_container_runtime.py`、`test_data_snapshot.py`、`test_data_status.py`、`test_factor_store.py`、`test_parquet_rewrite_cli.py` 等后期新增测试。

本设计按“先正确性、再文档事实、再结构清债”的顺序推进。所有拆分任务都保留公开入口，降低对现有 CLI、配置和 notebook 兼容路径的冲击。

## Goals / Non-Goals

**Goals:**

- 修复或配置化会影响回测可信度的预处理、基准、指标、缺失特征和 ST 状态语义。
- 让 README、AGENTS.md 和 docs 反映当前 CLI、测试、factor store、data status、data snapshot、parquet rewrite 和容器路径。
- 增加轻量文档测试，让新增测试文件、CLI 和内部链接不会再次从文档中遗漏。
- 给历史兼容入口、pickle 输入和双 CLI alias 建立清晰生命周期。
- 扩展低风险 Ruff 规则，并把大文件拆分记录为可按测试保护推进的任务。

**Non-Goals:**

- 本次不一次性拆完 `factor_store.py`、`runner.py`、`backtest.py`、`portfolio.py` 和 `data_sources/tushare.py`。
- 本次不移除现有公开 CLI alias。
- 本次不引入 DuckDB、Polars、Delta Lake 或新的数据湖依赖。
- 本次不实现完整 point-in-time ST、历史行业归属、退市股票全集和容量模型；只把当前语义表达清楚，并为后续真实数据源留接口。

## Decisions

### 1. 先修研究正确性，再扩展重构

把 `preprocess_data()` 填充范围、benchmark NAV 口径、total return 计算、缺失特征策略和 `is_st` 语义作为第一阶段。这些点会改变回测结果或用户对结果的解释，优先级高于文件拆分。

备选方案是先做大模块拆分，再修逻辑。该路径会扩大 diff，且拆分期间可能固化已有结果口径。当前选择先用测试保护正确性，再在稳定行为上拆模块。

### 2. 缺失特征默认失败，兼容路径显式放行

新增 `missing_feature_policy`，支持 `error`、`warn_fill_zero`、`fill_zero`。默认使用 `error`。`legacy_notebook_compat.yaml` 或迁移场景可以显式使用 `warn_fill_zero`。

备选方案是继续静默补 0 并只在日志中提示。该路径不能防止 factor store family 漏加载、外部 Alpha 缺列或配置拼写错误。

### 3. benchmark NAV 口径进入市场配置档

在市场配置档中声明 `benchmark_cum_ret` 口径，例如 `benchmark_cum_mode: nav` 或 `benchmark_cum_mode: cumulative_return`。`nav` 口径使用 `benchmark / first`，`cumulative_return` 口径使用 `1 + benchmark - first`。

备选方案是用数值范围自动推断口径。自动推断对指数、净值、累计收益和异常起点都有误判风险；显式配置更适合研究复现。

### 4. 总收益优先从 period returns 复利得到

当 `strategy_returns` 和 `benchmark_returns` 存在时，`compute_performance_metrics()` 应用 `(1 + ret).prod() - 1` 计算总收益和年化收益。NAV 仍用于回撤、图表和兼容路径。缺少 returns 时再回退到 NAV 首尾比值。

备选方案是在 `run_rolling_backtest()` 输出初始 NAV 点。该做法会改变 CSV 序列长度和日期约定，影响更多现有产物。优先修指标计算，后续可单独讨论初始点输出。

### 5. 文档测试只做事实和轻量风格检查

新增测试覆盖：

- `tests/test_docs_inventory.py`: `tests/test_*.py` 必须在 docs/testing.md 中登记。
- `tests/test_docs_console_scripts.py`: `pyproject.toml` 的 console scripts 必须在 README 或 docs 出现。
- `tests/test_docs_links.py`: README/docs 内部 Markdown 链接必须指向存在文件。
- `tests/test_docs_style.py`: 检查高风险句式和术语混用，保持低误报。

备选方案是引入 Vale 或 markdownlint。当前项目尚未使用文档 lint 依赖，先用 pytest 保持工具链简单。

### 6. 大文件拆分采用 facade 迁移

后续拆分 `runner.py`、`factor_store.py`、`backtest.py`、`portfolio.py` 和 `data_sources/tushare.py` 时，保留当前导入路径和公开函数。新模块先作为内部 helper 引入，测试通过后再逐步移动实现。

备选方案是直接把文件改成包并迁移所有 import。一次性移动会增加回归风险，也会干扰当前清债目标。

## Risks / Trade-offs

- [Risk] 缺失特征默认失败会暴露旧数据或旧配置中的隐性问题。→ Mitigation: 提供 `warn_fill_zero` 迁移策略，并在 legacy preset 中显式声明。
- [Risk] benchmark NAV 口径配置会影响历史指标。→ Mitigation: 为 `nav` 和 `cumulative_return` 都增加测试，并在 run_config/summary 中记录解析后的口径。
- [Risk] total return 改为 returns 复利后，现有测试期望需要更新。→ Mitigation: 增加专门测试说明首期收益纳入指标，并保留 NAV 回退路径。
- [Risk] 文档风格测试过严会影响正常写作。→ Mitigation: 只检查少数明确模式，测试失败信息给出文件和行号。
- [Risk] Ruff 规则扩展会带来较多机械改动。→ Mitigation: 分批开启 `I`、`UP`、`B`，每批单独运行 lint 和 tests。

## Migration Plan

1. 增加回测正确性测试，先用当前行为复现风险。
2. 修改 `preprocess_data()`、`build_benchmark_nav()`、`compute_performance_metrics()`、rolling/holdout 缺失特征处理和 TuShare ST 语义提示。
3. 更新配置 schema、默认配置、legacy preset、run_config 和 summary 输出。
4. 更新 README、AGENTS.md 和 docs，统一当前项目事实。
5. 增加文档库存和链接测试。
6. 分批扩展 Ruff 配置并完成必要格式调整。
7. 更新 docs/maintenance.md，将后续大文件拆分拆成可独立申请的 OpenSpec change。

Rollback 策略：回测行为变更均由配置开关保护。若旧实验需要复现，可在 legacy preset 中显式设置旧兼容策略并保留对应测试。

## Open Questions

- `benchmark_cum_ret` 在所有现有真实面板中的实际口径是净值/指数，还是累计收益率？实施前需要抽样检查当前数据或让用户确认。
- `is_st` 字段是否应立即重命名为 `is_st_latest_name_flag`，还是先保留字段名并增加 `st_source` 元数据与 warning？
- `moneytree` 单数 CLI alias 的下线周期是否需要日期承诺，还是仅标为长期兼容入口？
