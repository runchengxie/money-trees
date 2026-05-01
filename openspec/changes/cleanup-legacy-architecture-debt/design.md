## Context

Money Trees 的当前架构方向是健康的：核心包在 `src/moneytree/`，CLI、配置、市场 profile、因子、模型、组合、回测和文档都有明确分层；测试也覆盖了数据契约、CLI、因子仓库、TuShare、DolphinDB、文档 guard 和维护脚本。

问题集中在实现层的长期维护成本。静态行数显示多个核心文件已经超过合理单文件边界：`factor_store.py` 2188 行，`runner.py` 1534 行，`data_sources/tushare.py` 1069 行，`data.py` 880 行，`cli/dolphindb_alphas.py` 826 行，`data_status.py` 822 行。`docs/maintenance.md` 已经记录了相同方向的拆分建议，说明这不是单点观感，而是已经被项目维护文档识别的技术债。

兼容入口也需要统一生命周期管理：`scripts/build_dolphindb_alphas.py` 是正式 CLI 的 wrapper，`scripts/convert_pickle_to_parquet.py` 是旧 pickle 迁移脚本，`configs/preset/notebook_compat.yaml` 与 `legacy_notebook_compat.yaml` 内容一致但语义不同，`moneytree*` 单数 CLI alias 仍用于兼容。`factors/ops.py` 有测试覆盖但没有从 `moneytree.factors` 顶层导出，需要明确其 internal/public 定位。

## Goals / Non-Goals

**Goals:**

- 建立可执行的代码健康治理规则，而不只是记录一份重构建议。
- 渐进拆分核心大文件，优先降低 `runner.py` 和 `factor_store.py` 的职责集中度。
- 保持 `moneytree` Python 导入路径、`moneytrees` 新 CLI、`moneytree*` 兼容 CLI 和现有测试承诺可用。
- 为 legacy wrapper、pickle 迁移、notebook compatibility preset、因子算子工具建立状态和迁移路径。
- 引入更严格但可分阶段落地的质量门禁，避免一次性全仓库重写。

**Non-Goals:**

- 不重写 Alpha101/191/158/360 计算逻辑。
- 不改变 `date, ticker` canonical 面板形状。
- 不删除 `data/`、`artifacts/`、cache、因子仓库或本地运行产物。
- 不在本变更中移除仍有测试、文档或外部兼容价值的 CLI alias。
- 不把所有大文件一次性拆完；后续模块按风险和测试覆盖分批治理。

## Decisions

1. **Facade-preserving split is the default.**

   `moneytree.runner` and `moneytree.factor_store` remain import-compatible facades while implementation moves into cohesive submodules. This avoids forcing downstream code to update imports during a maintenance refactor. The alternative, direct file renaming and import migration, would create unnecessary breaking risk for little short-term benefit.

2. **Classify compatibility surfaces before removal.**

   Each historical entry point gets one of: `active`, `compatibility`, `deprecated`, or `removal-candidate`. A deprecated or removal-candidate item must have a documented replacement and test coverage for the warning or migration path. The alternative, deleting low-use files immediately, is risky because CLI scripts and presets can be referenced from notebooks, cron jobs, or old research artifacts outside the repository.

3. **Prioritize central-path modules before peripheral cleanup.**

   The first implementation slice should update docs and compatibility classification, then split `runner.py` outputs/holdout/summary helpers, then split `factor_store.py` manifest/validation helpers. These modules sit on the main research and factor-store paths, so reducing their coupling lowers the cost of later changes. Smaller one-off cleanups should not consume the whole change before central risk is reduced.

4. **Quality gates start as audit, then become enforcement per touched area.**

   Ruff currently selects `E/F/I/UP/B` and ignores `E501`, so style hygiene exists but line length and complexity are weakly enforced. Add candidate checks such as complexity and simplification in a documented audit first, then enable or locally fix them for modules being refactored. The alternative, enabling many new rules globally in one patch, would mix mechanical churn with behavioral refactors and make review harder.

5. **Legacy behavior remains tested until explicitly archived.**

   Tests that currently assert wrapper behavior, transitional presets, pickle migration, optional dependencies, and factor-store contracts should be preserved or replaced with more precise migration tests. Removing tests only after deleting behavior keeps compatibility decisions visible.

6. **`factors/ops.py` must be either explicitly internal or promoted.**

   The file is currently used by tests and contains generic wide-matrix alpha operators, but it is not exported by `moneytree.factors.__all__`. The implementation should choose one path: document it as an internal helper with focused tests, or expose selected stable operators as public API. Leaving it ambiguous invites accidental dependency.

## Risks / Trade-offs

- [Risk] Facade-preserving splits can leave thin wrappers that look redundant. → Mitigation: keep facades minimal, documented, and covered by import/CLI tests.
- [Risk] Hidden external users may rely on old script paths or preset names. → Mitigation: deprecate with replacement guidance before removal, and keep aliases through at least one documented transition.
- [Risk] Refactoring central modules can introduce subtle data contract regressions. → Mitigation: run focused factor-store, backtest CLI, data contract, and snapshot/status tests for each slice.
- [Risk] Adding strict lint rules globally can cause noisy churn. → Mitigation: stage lint expansion as an audit and only enforce new rules on touched modules until backlog is reduced.
- [Risk] Large-file拆分 can create more files without improving cohesion. → Mitigation: split only along stable responsibilities already identified in maintenance docs: manifest, validation, partitioning, writer, loader, outputs, holdout, summary.

## Migration Plan

1. Add a code health governance spec and update maintenance docs with current audit evidence.
2. Classify legacy entry points and add visible deprecation guidance where needed.
3. Refactor `runner.py` by extracting outputs, holdout, and run summary helpers behind the existing `run_backtest()` facade.
4. Refactor `factor_store.py` by extracting manifest and validation helpers first, then writer/loader modules in later tasks.
5. Evaluate expanded Ruff rules and document which checks are enforced immediately versus tracked as backlog.
6. Run targeted tests after each slice and full `uv run pytest -q` before considering the change complete.

## Open Questions

- Should `configs/preset/notebook_compat.yaml` remain as a permanent alias or emit a deprecation warning in the config loader?
- Should `scripts/convert_pickle_to_parquet.py` remain as a minimal trusted-data helper, or should documentation route all migration through `moneytrees-parquet-rewrite`?
- Should selected `factors/ops.py` operators become public API, or should all new factor generation continue through `factors/qlib.py` and external DolphinDB paths?
