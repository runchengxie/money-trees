# 架构设计

本文说明 Money Trees 当前实现的分层、数据流和保存策略。项目定位是 A 股经典 Alpha 截面选股研究与回测工具，核心目标是把 810 因子列契约、数据契约、模型选择、组合构建和结果输出拆开维护。

## 总览

```text
TuShare / 外部数据
-> 标准 date,ticker 面板
-> 市场配置档校验与可交易过滤
-> 因子生成或并入
-> 特征滞后
-> 模型适配器训练
-> 组合权重构建
-> 滚动回测和 holdout
-> 指标、CSV、JSON 和报告产物
```

当前默认配置栈：

```text
configs/market/cn.yaml
configs/model/rf.yaml
configs/backtest/default.yaml
```

## 数据层

相关模块：

- `src/moneytree/data.py`
- `src/moneytree/data_sources/tushare.py`
- `src/moneytree/factor_store.py`
- `scripts/convert_pickle_to_parquet.py`

职责：

- 读取可信 pickle 或 parquet。
- 统一 `date, ticker` 索引。
- 生成 `rel_return` 和 `rel_performance`。
- 处理缺失值、无穷值和特征滞后。
- 将 TuShare 日频接口标准化为项目面板。
- 将原始接口结果按 API 和交易日缓存为 parquet。
- 通过因子仓库保存基础面板、本地因子、外部因子、分区文件和元数据清单。

标准输入是 `date, ticker` 面板。上游数据可以先保留普通列，运行时会转成 MultiIndex。详细列契约见 [data_contract.md](data_contract.md)。

## 市场层

相关模块：

- `src/moneytree/markets/base.py`
- `src/moneytree/markets/cn.py`
- `src/moneytree/markets/registry.py`
- `configs/market/cn.yaml`

职责：

- 维护市场配置档，目前只有 `cn`。
- 归一化基准收益列和基准净值列。
- 校验标签、基准和可交易过滤字段。
- 过滤停牌、ST、涨停和跌停样本。

`cn` 默认使用：

- 基准收益列：`benchmark_next_period_return`
- 基准累计列：`benchmark_cum_ret`
- 标签来源：`actual`
- 特征滞后：`feature_lag_periods=1`

## 因子层

相关模块：

- `src/moneytree/factors/qlib.py`
- `src/moneytree/factors/catalog.py`
- `src/moneytree/factors/evaluate.py`
- `src/moneytree/cli/factor_store.py`
- `docs/factor_catalog.csv`

职责：

- 生成本地 Alpha158-style 和 Alpha360-style 日频特征，共 518 列。
- 维护 Alpha101、Alpha191、Alpha158、Alpha360 共 810 列的列名和接入口径。
- 计算单因子 IC 和 RankIC。
- 将 Alpha158/360 和外部 Alpha101/191 写入因子仓库，供回测按 family 或 prefix 按需读取。

Alpha101 和 Alpha191 共 292 列，公式值由外部实现生成后写入因子仓库或兼容并入面板。本仓库维护列名约定、输入字段、校验、元数据清单和治理提醒；回测读取离线产物。

## 模型层

相关模块：

- `src/moneytree/models/base.py`
- `src/moneytree/models/random_forest.py`
- `src/moneytree/models/linear.py`
- `src/moneytree/models/xgboost.py`
- `src/moneytree/models/registry.py`
- `configs/model/*.yaml`

内置模型：

- `random_forest`: 分类目标 `rel_performance`，支持调参和特征选择。
- `xgboost`: 分类目标 `rel_performance`，依赖 `xgboost` extra。
- `xgboost_regressor`: 回归目标 `rel_return`，依赖 `xgboost` extra。
- `ridge`、`lasso`、`elasticnet`: 回归目标 `rel_return`，线性基准模型。

模型适配器统一提供：

- 默认参数。
- 训练目标列。
- 训练方法。
- 输出分数、离散预测和概率。
- 支持的调参与特征选择能力。

默认模型配置不启用 Optuna 调参。需要调参时叠加 `configs/preset/tuning.yaml`，并安装 `tuning` 或 `research` extra。

## 组合层

相关模块：

- `src/moneytree/portfolio.py`
- `configs/backtest/default.yaml`

职责：

- 将模型输出转换成连续信号。
- 按股票聚合信号，重复 ticker 默认取最后一条观测。
- 支持启发式权重和 `signal_risk_qp` 二次规划权重。
- 控制总暴露、净暴露、单票上限和最小持仓数量。
- 支持训练窗口波动率缩放、粗粒度行业中性和换手惩罚。

默认权重方法是 `heuristic`。`signal_risk_qp` 会使用训练窗口收益估计协方差，求解失败时默认回退到启发式方法。

## 回测层

相关模块：

- `src/moneytree/backtest.py`
- `src/moneytree/runner.py`
- `src/moneytree/cli/backtest.py`

职责：

- 构造滚动训练、间隔和测试窗口。
- 分别拟合 segment A 与 segment B。
- 拼接两个 segment 的样本外序列。
- 生成策略、信号、基准、换手、持仓数、IC 和 RankIC。
- 记录目标/实际暴露、未分配暴露和 QP fallback 诊断。
- 计算收益、波动、回撤、IR、VaR、CVaR、Alpha/Beta 等指标。
- 按配置执行最终 holdout 验证。

当前固定的 segment 拟合区间在 `src/moneytree/runner.py` 中定义，滚动窗口数量、训练月数、间隔月数和测试月数由配置控制。

## 输出层

相关模块：

- `src/moneytree/runner.py`
- `docs/outputs.md`

默认输出目录由 `output.output_dir` 或 `--output-dir` 控制。核心产物包括：

- `metrics.json`
- `run_config.json`
- `experiment_manifest.json`
- `run_summary.txt`
- 策略、信号和基准净值 CSV
- 样本外诊断 CSV
- Notebook 风格报告数据
- segment 特征清单
- 可选 holdout 子目录

`run_config.json` 记录解析后的配置、基准净值口径、segment 规格、segment 验证区间、holdout 信息、git commit 和可复现摘要。`experiment_manifest.json` 记录输入文件 hash、raw 输入 schema hash、模型输入 schema hash、配置文件 hash、解析后配置 hash、数据版本和运行环境。

## 数据保存策略

当前实现采用三层保存：

- 原始缓存：TuShare 按 `api_name/trade_date=YYYYMMDD.parquet` 保存接口返回。
- 缓存索引：`manifest.sqlite` 记录 API、交易日、路径、行数、列信息和创建时间。
- 因子仓库：`manifest.json` 记录基础面板、因子 family、分区文件、schema 和生成参数。
- 研究产物：标准面板 parquet、回测 CSV、JSON 和文本摘要。

这个方向适合当前项目规模，raw cache 可复用，标准面板可重建，回测产物可审计。当前已经落地的版本和元数据：

- TuShare raw cache 的请求参数 hash、schema hash、content hash、创建时间和更新时间。
- 回测输入文件 SHA-256。
- raw 输入面板和模型输入面板 schema hash。
- 配置文件集合 hash 和解析后配置 hash。
- 派生 `dataset_version`。
- Python 包版本和随机种子。

后续可以继续补充：

- 输出文件 hash。
- TuShare token label，避免记录明文 token。
- 外部因子生成器版本。
- 标准面板生成参数的独立 dataset metadata。

DuckDB、Polars、Delta Lake、LakeFS 等技术可以在数据规模和多人协作压力上来后再评估。现阶段更高收益的改进是完善元数据和数据分层。
