## Why

当前项目的因子清单覆盖 Alpha101、Alpha191、Alpha158、Alpha360 共 810 个列名，但项目内只实现 Alpha158 和 Alpha360 共 518 个本地计算特征。Alpha101 和 Alpha191 目前是外部并入口径，缺少正式的外部生成流程、manifest、列完整性校验和 WSL/Docker 开发说明，容易让研究者误以为 810 个因子都已在本仓库内可计算。

这个 change 将 DolphinDB 定位为 Alpha101/191 的离线外部因子生产器，并把输出固化为可复现的 parquet 面板输入，让 `money-tree` 继续专注于数据契约、特征滞后、模型训练、组合构建和回测。

## What Changes

- 新增 DolphinDB Alpha101/191 离线生成脚本，用于读取标准 `date, ticker` 面板、映射 DolphinDB 所需字段、调用外部模块并合并输出。
- 新增外部因子 manifest，记录输入/输出 hash、DolphinDB 版本、模块版本、价格/成交量/市值/行业/基准字段口径和生成时间。
- 新增 Alpha101/191 输出校验，要求列名完整且符合 `alpha101_001...alpha101_101`、`alpha191_001...alpha191_191`，并保证 `date, ticker` 键唯一。
- 新增 DolphinDB/WSL/Docker 文档，说明推荐的单节点 Docker Desktop + WSL 2 开发路径、模块挂载目录、字段映射、运行命令和风险口径。
- 保持 Alpha158/Alpha360 的本地生成方式不变；Alpha101/Alpha191 不进入 `add_factor_family_features()` 的本地计算路径。
- 保持回测主流程只消费已生成的 parquet，不在回测运行时请求 DolphinDB。

## Capabilities

### New Capabilities

- `external-alpha-production`: Define the contract and workflow for generating external Alpha101/Alpha191 factor columns, validating them, recording provenance, and merging them into the standard panel.

### Modified Capabilities

None.

## Impact

- Affected code:
  - `scripts/build_dolphindb_alphas.py` or an equivalent project tool for external Alpha101/191 production.
  - Potential helper module under `src/moneytree/factors/` for external alpha column naming, validation, manifest generation, and merge behavior.
  - Tests covering column validation, manifest contents, field mapping, duplicate key rejection, and script-level smoke behavior.
- Affected documentation:
  - New `docs/dolphindb_alpha101_191.md`.
  - Updates to `docs/factor_catalog.md`, `docs/data_contract.md`, and cookbook/runbook references if needed.
- Dependencies:
  - DolphinDB server remains external to the core package.
  - DolphinDB Python client should be optional and fail with a clear message when not installed.
  - Docker Desktop/WSL guidance is documentation and local infrastructure, not a runtime requirement for normal backtests.
- Data and artifacts:
  - Generated Alpha101/191 parquet files and manifest JSON files are runtime outputs and should not be committed.
  - No TuShare token, `.env`, raw cache, or generated data should be printed or committed.
