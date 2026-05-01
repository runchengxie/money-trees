## Why

项目已经完成大量功能补齐，当前主要风险从“缺功能”转为“核心路径继续膨胀导致后续修改成本上升”。现有维护文档和静态检查都指向同一问题：`factor_store.py`、`runner.py`、TuShare 数据源、DolphinDB CLI、回测和组合模块已经承担过多职责，同时仍保留若干历史兼容入口和迁移脚本，需要一次有边界的治理。

## What Changes

- 建立一套代码健康治理准则，用于判断哪些历史入口继续保留、标记 deprecated、迁移到正式 CLI，或在后续版本删除。
- 将大文件拆分作为渐进式内部重构执行，优先处理 `runner.py` 和 `factor_store.py`，保留原有 facade 和公开导入路径。
- 梳理一次性脚本、历史 preset、pickle 迁移、`moneytree` 单数 CLI alias、legacy notebook 兼容路径和因子算子工具的生命周期。
- 增加或调整维护测试，确保重构不改变 `date, ticker` 面板契约、因子仓库元数据清单、CLI 行为和可选依赖错误提示。
- 收紧代码质量门槛，先以非破坏方式引入复杂度、未使用参数、return 简化等 Ruff 规则评估，再按模块治理逐步启用。
- 不做算法重写，不改变默认研究路径，不移除仍有测试或文档承诺的兼容入口。

## Capabilities

### New Capabilities
- `code-health-governance`: 定义维护性审计、历史兼容入口生命周期、大文件拆分和质量门禁的项目规则。

### Modified Capabilities
- None.

## Impact

- Affected code: `src/moneytree/runner.py`, `src/moneytree/factor_store.py`, `src/moneytree/data_sources/tushare.py`, `src/moneytree/data.py`, `src/moneytree/cli/dolphindb_alphas.py`, `src/moneytree/data_status.py`, `src/moneytree/backtest.py`, `src/moneytree/portfolio.py`, `src/moneytree/model.py`, `src/moneytree/factors/ops.py`.
- Affected compatibility surfaces: `scripts/convert_pickle_to_parquet.py`, `scripts/build_dolphindb_alphas.py`, `configs/preset/notebook_compat.yaml`, `configs/preset/legacy_notebook_compat.yaml`, pickle input support, `moneytree*` CLI aliases.
- Affected docs and tests: `docs/maintenance.md`, `docs/testing.md`, `docs/configuration.md`, `docs/data_contract.md`, `tests/test_factor_store.py`, `tests/test_backtest_cli.py`, `tests/test_build_dolphindb_alphas_script.py`, `tests/test_convert_pickle_to_parquet_script.py`, and focused tests for modules being split.
- Public APIs should remain source compatible during the initial implementation: existing imports from `moneytree.runner`, `moneytree.factor_store`, and existing console scripts continue to work unless a later change explicitly marks a breaking removal.
