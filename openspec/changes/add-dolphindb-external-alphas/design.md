## Context

`money-tree` 当前以标准 `date, ticker` 面板为核心数据契约。因子层已经本地实现 Alpha158-style 和 Alpha360-style 特征，同时在因子清单中维护 Alpha101、Alpha191、Alpha158、Alpha360 共 810 个列名。

当前边界是清楚的：Alpha158/360 由 `moneytree.factors.qlib` 本地生成，Alpha101/191 的 `local_generation` 是 `external`，并要求外部生成后并入面板。但 Alpha101/191 还没有正式的生产脚本、输出校验、manifest 和操作文档。用户在 WSL 环境开发，适合把 DolphinDB 作为独立单节点 Docker 服务使用，再把生成结果落成 parquet 给回测消费。

相关约束：

- 标准面板形状必须继续使用 `date, ticker`。
- 回测主链路必须继续统一应用 `feature_lag_periods`。
- DolphinDB、TuShare token、raw cache、生成数据和 manifest 都不能被提交。
- DolphinDB Python client 必须是可选依赖，未安装时给出清晰错误。
- Alpha158/360 不迁移到 DolphinDB，本地实现继续保留。

## Goals / Non-Goals

**Goals:**

- 提供一个离线 Alpha101/191 生产入口，读取现有 parquet 面板并输出合并后的 parquet。
- 将项目字段映射到 DolphinDB WQ101/GTJA191 所需字段，包括复权价格、成交量、市值、行业和基准开收盘字段。
- 生成可审计 manifest，记录输入输出 hash、版本、字段口径、因子家族和生成时间。
- 在合并前校验 Alpha101/191 的列名、列数、键唯一性和面板对齐。
- 文档化 WSL + Docker Desktop + DolphinDB 单节点容器的推荐开发路径。
- 保持回测只依赖最终 parquet，不在训练或回测时实时调用 DolphinDB。

**Non-Goals:**

- 不在本仓库内移植 292 个 Alpha101/191 公式。
- 不承诺 Alpha101/191 与任意第三方 Python 实现数值一致。
- 不实现 DolphinDB 官方模块本身，也不把 `.dos` 模块文件提交到仓库。
- 不把 DolphinDB 加入核心安装依赖。
- 不改变 Alpha158/360 当前本地生成语义。
- 不解决 point-in-time 行业分类数据源；本 change 只记录并暴露该口径风险。

## Decisions

### 1. DolphinDB 作为离线上游生产器

实现方式：

- 新增脚本 `scripts/build_dolphindb_alphas.py`。
- 输入：标准 `date, ticker` parquet 面板。
- 输出：包含 `alpha101_*`、`alpha191_*` 列的合并 parquet，以及同名或旁路 manifest JSON。
- DolphinDB 连接参数通过 CLI 参数传入，默认连接 `127.0.0.1:8848`。

理由：

- 当前架构已经支持“因子生成或并入”。
- 固定 parquet 输入能让回测可复现、可 hash、可归档。
- 回测运行时不依赖 DolphinDB，降低训练链路脆弱性。

替代方案：

- 回测过程中动态调用 DolphinDB：更难复现、更慢，也会把外部服务耦合进主链路。
- 直接把公式移植进 pandas：短期成本高，且 rank、decay、SMA、缺失值语义容易偏离基准口径。

### 2. 增加轻量外部因子 helper

实现方式：

- 新增 `src/moneytree/factors/external.py`，集中放置：
  - `alpha101_001...alpha101_101` 和 `alpha191_001...alpha191_191` 列名生成。
  - 外部因子列完整性校验。
  - `date, ticker` 键唯一性校验。
  - 输入字段映射和口径摘要。
  - manifest 结构构建。

理由：

- 脚本和测试可以复用同一套契约。
- 避免把列名和校验逻辑散落在 CLI 脚本、文档和测试里。

替代方案：

- 只在脚本内实现：初期更快，但难以测试和复用。

### 3. Optional dependency 而不是核心依赖

实现方式：

- 新增 optional dependency，例如 `dolphindb = ["dolphindb"]`。
- `scripts/build_dolphindb_alphas.py` 在导入失败时提示安装对应 extra。
- 核心回测、Alpha158/360 和 TuShare 流程不要求安装 DolphinDB Python client。

理由：

- 维持当前可选依赖风格。
- 没有外部因子需求的用户不应被 DolphinDB 客户端影响安装。

替代方案：

- 将 `dolphindb` 加入核心 dependencies：简单但扩大默认安装面。
- 加入 `research` extra：方便研究环境，但可能让 `research` 变得过重。可以后续再决定是否把 `research` 包含 DolphinDB extra。

### 4. 字段映射显式化

映射规则：

- `tradetime` <- `date`
- `securityid` <- `ticker`
- `open/high/low/close/vwap` 优先使用对应 `_adj` 列，缺失时回退原始列。
- `vol` <- `volume`，缺失时允许从 `vol * 100` 派生。
- `cap` <- `circ_mv`，缺失时回退 `total_mv`，仍缺失则允许全空并在 manifest 标注。
- `indclass` <- `industry`，缺失时填 `"UNKNOWN"` 并在 manifest 标注。
- `index_open/index_close` <- `benchmark_open/benchmark_close`，缺失时填空并在 Alpha191 运行前报错或显式跳过需要基准的 family。

理由：

- 与 TuShare 标准面板和本地 Alpha158/360 复权价格偏好保持一致。
- manifest 记录实际选择，避免未来回测结果不可解释。

### 5. DolphinDB 服务和模块不进入仓库版本控制

实现方式：

- 文档推荐 Windows 安装 Docker Desktop，启用 WSL 2 backend，在 WSL 项目目录执行 Docker 命令。
- 建议本地目录 `infra/dolphindb/modules`、`infra/dolphindb/data`、`infra/dolphindb/logs`，并在 `.gitignore` 或文档中明确 runtime 输出不提交。
- 官方或用户自行获取的 DolphinDB `.dos` 模块放在本地挂载目录；仓库只记录需要的模块文件名和版本字段。

理由：

- 避免提交第三方模块、license 相关内容和本地运行数据。
- WSL 中通过 Docker Desktop 管理容器，减少手动维护 Linux Docker daemon 的成本。

## Risks / Trade-offs

- [Risk] DolphinDB 模块版本或语义变化导致因子值变化。  
  Mitigation: manifest 必须记录 DolphinDB server version、Python client version、WQ101/GTJA191 module version 或用户提供的 module label。

- [Risk] 行业字段不是 point-in-time，Alpha101 行业相关因子可能有未来信息污染。  
  Mitigation: manifest 必须记录 `industry_field` 和口径备注；文档明确该风险，后续可接 point-in-time 行业表。

- [Risk] 字段缺失时静默生成大量空因子。  
  Mitigation: family 运行前做 required inputs 校验；允许 fallback 的字段必须写入 manifest；不可满足的字段应报错。

- [Risk] 输出列不完整但回测仍能运行。  
  Mitigation: 对请求的 family 强制校验精确列集合和列数，缺失或多余时失败。

- [Risk] Docker/DolphinDB 环境安装阻碍研究验证。  
  Mitigation: 文档先提供 WSL + Docker Desktop 单节点路径；脚本保持连接参数可配置，允许用户连接远端 DolphinDB。

- [Risk] 生成 parquet 与输入面板键不匹配。  
  Mitigation: 合并前校验 `date, ticker` 键唯一；合并后记录匹配率、alpha 缺失率和输出行数。

## Migration Plan

1. 实现 helper、脚本、manifest 和校验测试。
2. 增加可选 DolphinDB 依赖说明，但不要求默认安装。
3. 新增 DolphinDB Alpha101/191 文档和 WSL/Docker 运行说明。
4. 更新因子清单文档，强调 810 行是 catalog 覆盖范围，其中 Alpha101/191 是外部生成并入口径。
5. 用户生成新的 Alpha101/191 parquet 后，在现有 `moneytree` CLI 中用 `--data` 指向该 parquet 运行回测。

Rollback:

- 不使用新脚本即可回到当前状态。
- 回测主流程没有运行时 DolphinDB 依赖，因此回滚只需删除或忽略生成的外部因子面板。

## Open Questions

- 是否将 `dolphindb` extra 纳入 `research` extra，还是保留为单独 extra。
- DolphinDB 侧是否需要维护一个本地 `moneytreeAlpha.dos` 包装模块，还是第一版由 Python 脚本逐个调用官方模块函数。
- module version 如何从 `.dos` 文件可靠读取；如果无法读取，第一版可要求用户通过 CLI 参数提供 `--wq101-module-version` 和 `--gtja191-module-version`。
- Alpha191 在缺少 `benchmark_open/benchmark_close` 时是否整体失败，还是只允许生成不依赖基准字段的子集。第一版建议整体失败，避免输出含义不完整。
