# 截面随机森林

基于脚本且具备可复现回测流程的截面随机森林策略研究项目。

## 文档范围

- 本文档重点覆盖 `scripts/run_backtest.py` 的输入要求、策略假设、参数与产物说明。
- 项目中的辅助脚本（如 `scripts/convert_pickle_to_parquet.py`）与参考文件（`reference_notebook/notebook.ipynb`）会简要说明，但不作为完整技术规范。

## 环境配置

- Python: `>=3.10`
- 依赖管理器: `uv`

安装依赖：

```bash
uv sync --dev
```

## 数据要求

输入文件可以是 `.pkl` 或 `.parquet` 格式，并且必须包含以下内容：

- 索引键：`date`（日期）、`ticker`（股票代码）（作为列或 MultiIndex 均可）
- 收益率/基准列：
  - `next_period_return`
  - `spy_next_period_return`
  - `spy_cum_ret`
- 特征列：除了 `NON_FEATURE_COLUMNS` 中列出的保留字段外，所有的数值型/布尔型列

数据加载器会将数据标准化为经过排序的 `('date', 'ticker')` MultiIndex（多重索引）。

如需先将原始 `.pkl` 数据转换为 parquet，可使用：

```bash
uv run python scripts/convert_pickle_to_parquet.py --input data_small.pkl
```

## 策略定义与假设

- 标签来源：
  - `actual`（默认）：`next_period_return - spy_next_period_return`（超额收益）
  - `pred_rel_return`：使用预先计算好的 `pred_rel_return`
- 标签映射（`--label-threshold`，默认值为 `0.05`）：
  - `> 阈值 -> +1`
  - `< 负阈值 -> -1`
  - 其他情况 `-> 0`
- 仓位管理：
  - `--portfolio-weighting-method` 支持两种模式：
    - `heuristic`（默认）：原有规则式多空配权
    - `signal_risk_qp`：信号驱动 + 风险约束二次优化（QP）
  - 先将模型输出映射为连续信号（默认使用 `predict_proba` 的 `P(+1)-P(-1)`）
  - 横截面阈值过滤（`--portfolio-min-score`）+ z-score 截断（`--portfolio-winsor-z`）
  - 可选 train-window 波动率缩放（`--portfolio-vol-scaling` / `--portfolio-vol-power`）
  - 在单票上限（`--portfolio-max-name-weight`）下分配多空权重，并约束总杠杆/净敞口（`--portfolio-gross-target` / `--portfolio-net-target`）
  - 可选粗粒度行业去均值（`--portfolio-sector-neutral`）
  - 当使用 `signal_risk_qp` 时：
    - 使用 rank-based 信号映射构建 `mu`
    - 使用训练窗口收益协方差（可选 Ledoit-Wolf 收缩）
    - 目标函数同时考虑信号收益、风险惩罚和相对上一期权重的 L2 换手惩罚
    - 约束包含净敞口、总敞口上限、单票权重上限；求解失败时可回退到 `heuristic`
- 交易成本：
  - 换手率（turnover）估算方式为：
    - `0.5 * sum_i |w_t,i - w_(t-1),i|`
  - 每期扣除的成本为 `turnover * cost_bps / 10000`
  - 调参（Optuna）、特征选择与滚动回测统一使用上述成本口径；单期验证默认按“从空仓建仓”的方式估算换手

## 数据泄露处理

缺失值的中位数填充，现在会在每个训练窗口（train window）上进行拟合，然后再应用到验证/测试窗口（valid/test windows）中。

处理流程：

1. 全局安全步骤：无穷大值（inf）替换为 NaN、按股票代码前向填充（forward-fill）、标签构建
2. 逐窗口拟合/转换（fit/transform）：
   - 在训练数据切片上拟合计算中位数
   - 将训练集计算出的中位数应用到训练/验证/测试数据切片上

这避免了使用全局中位数导致用到未来数据（即数据泄露）。

可选地，你可以使用 `--feature-lag-periods` 对所有模型特征按 ticker 进行额外滞后（lag）来做泄露敏感性测试（例如 `0/1` 对比）。

## 运行回测

基础示例：

```bash
uv run python scripts/run_backtest.py \
  --data data_small.parquet \
  --output-dir artifacts/backtest \
  --feature-selection importance \
  --n-trials 50 \
  --cost-bps 10
```

进阶示例（时间序列 CV 调参 + 最终 holdout OOS）：

```bash
uv run python scripts/run_backtest.py \
  --data data_small.parquet \
  --output-dir artifacts/backtest \
  --feature-selection importance \
  --n-trials 50 \
  --tuning-cv-folds 3 \
  --holdout-start 2023-01-01 \
  --holdout-end 2024-07-01 \
  --holdout-model-segment segment_b \
  --cost-bps 10
```

## 主要参数

- `--data`：输入的 `.pkl`/`.parquet` 文件路径
- `--output-dir`：输出文件夹
- `--label-source`：`actual` 或 `pred_rel_return`
- `--label-threshold`：标签划分阈值
- `--add-missing-indicators`：添加 `__is_missing` 数值型指示变量（标志缺失值）
- `--cost-bps`：以基点（bps）为单位的交易成本
- 组合构建参数：
  - `--portfolio-min-score`, `--portfolio-winsor-z`
  - `--portfolio-weighting-method`
  - `--portfolio-gross-target`, `--portfolio-net-target`
  - `--portfolio-max-name-weight`, `--portfolio-min-names-per-side`
  - `--portfolio-vol-scaling`, `--portfolio-vol-power`
  - `--portfolio-sector-neutral`, `--portfolio-sector-prefix`
  - `signal_risk_qp` 相关：
    - `--portfolio-qp-risk-aversion`, `--portfolio-qp-turnover-penalty`
    - `--portfolio-qp-cov-lookback`, `--portfolio-qp-cov-shrinkage`, `--portfolio-qp-cov-ridge`
    - `--portfolio-qp-mu-clip`, `--portfolio-qp-max-names`
    - `--portfolio-qp-solver-max-iter`, `--portfolio-qp-solver-ftol`
    - `--portfolio-qp-fallback-to-heuristic`
- `--n-trials`：用于随机森林调参的 Optuna 试验次数
- `--tuning-cv-folds`：调参时的时间序列 CV 折数（`1` 表示关闭 CV，使用单验证集）
- `--feature-selection`：特征选择方式（`none` / `importance` / `sequential`）
- `--min-features`：序列特征选择（sequential selection）的特征数量下限
- `--max-selection-steps`：序列特征选择循环的最大步数限制
- `--random-seed`：随机种子
- `--feature-lag-periods`：按 ticker 对全部特征额外滞后 N 期（默认 `0`）
- 滚动窗口控制：
  - `--train-months`（训练期月数）
  - `--gap-months`（间隔期月数）
  - `--test-months`（测试期月数）
- 数据段控制：
  - `--segment1-start`, `--segment1-windows`
  - `--segment2-start`, `--segment2-windows`
- 独立 holdout 控制（可选）：
  - `--holdout-start`, `--holdout-end`
  - `--holdout-model-segment`（`segment_a` / `segment_b`）
- `--export-parquet`：保存全局预处理后 parquet 文件的可选路径

## 运行时间预估（CPU）

当前实现使用 `sklearn.RandomForestClassifier`，默认在 **CPU** 上运行（不依赖 GPU）。

在 `data_small.parquet`（约 14.1 万行、1231 个特征）上，基于 `Intel Core i5-7500 (4C/4T)` 的实测参考如下：

- `--feature-selection importance --n-trials 1 --segment1-windows 0 --segment2-windows 0`：约 `24s`
- `--feature-selection importance --n-trials 1 --segment1-windows 5 --segment2-windows 5`：约 `74s`
- `--feature-selection importance --n-trials 3 --segment1-windows 2 --segment2-windows 2`：约 `78s`
- 默认参数（`--n-trials 50`，`60 + 20` 个滚动窗口，`importance`）：预计约 `17~22 分钟`

说明：

- 实际耗时会随数据规模、磁盘速度、当前 CPU 负载、特征选择方式波动。
- 若启用 `--tuning-cv-folds > 1`，调参耗时会近似按折数增加。
- 若启用 `--holdout-start/--holdout-end`，会额外执行一段独立 holdout 评估，整体耗时进一步上升。
- 若使用 `--feature-selection sequential`，耗时通常会显著增加（可能到 1 小时以上）。
- 若只想先验证流程，建议先用小参数快速跑通（例如 `--n-trials 1 --segment1-windows 1 --segment2-windows 1`）。

## 输出结果

- `strategy_nav.csv`
- `spy_nav.csv`
- `strategy_returns.csv`
- `spy_returns.csv`
- `strategy_turnover.csv`（每个 OOS 期的换手率）
- `active_names.csv`（每个 OOS 期的活跃标的数量）
- `ic_series.csv`（每个 OOS 期的 `period_ic` 与 `period_rank_ic`）
- `oos_period_diagnostics.csv`（OOS 期级别诊断表：收益、换手、活跃数、IC）
- `strategy_vs_spy.csv`
- `metrics.json`
- `run_config.json`（记录本次运行参数、分段配置、时间戳与可用的 git commit）
- `run_summary.txt`（面向人的简要总结：年化收益、波动率、回撤、Sortino/Calmar、VaR/CVaR、IC、换手等）
- `segment_a_features.txt`
- `segment_b_features.txt`
- 可选独立 holdout 输出（启用 `--holdout-start/--holdout-end` 时）：
  - `holdout/strategy_nav.csv`
  - `holdout/spy_nav.csv`
  - `holdout/strategy_returns.csv`
  - `holdout/spy_returns.csv`
  - `holdout/strategy_turnover.csv`
  - `holdout/active_names.csv`
  - `holdout/ic_series.csv`
  - `holdout/oos_period_diagnostics.csv`
  - `holdout/strategy_vs_spy.csv`
  - `holdout/metrics.json`
  - `holdout/holdout_config.json`
- 可选的特征选择历史记录：
  - `segment_a_selection_history.csv`
  - `segment_b_selection_history.csv`

说明：仓库中的 `artifacts/backtest_*` 属于历史示例产物快照，数值可能与当前代码版本或当前参数不完全一致；请以你本次运行输出为准。

## 指标定义 (`metrics.json`)

- `metrics.json` 包含两类字段：`segment_*`（分段拟合诊断）和主回测指标（策略 vs SPY）。

分段拟合诊断（`segment_*`）：

- `segment_a_validation_profit` / `segment_b_validation_profit`：分段验证期组合收益（含成本）；用于看调参后的验证期表现，越高通常越好。
- `segment_a_validation_turnover` / `segment_b_validation_turnover`：分段验证期换手率；越高代表交易更频繁、对成本更敏感。
- `segment_a_validation_active_names` / `segment_b_validation_active_names`：分段验证期活跃标的数；越大通常代表覆盖更分散。
- `segment_a_tuning_best_value` / `segment_b_tuning_best_value`：该分段 Optuna 最优目标值（训练窗口上的调参目标）；用于看调参搜索质量，不等同于最终 OOS 指标。
- `segment_a_feature_count` / `segment_b_feature_count`：该分段最终特征数量；用于判断模型复杂度与稳定性。

收益与风险（策略 vs SPY）：

- `strategy_total_return` / `spy_total_return`：区间总收益（`NAV_end / NAV_start - 1`）；先看策略是否跑赢基准。
- `strategy_annualized_return` / `spy_annualized_return`：年化收益；用于横向比较不同区间长度结果。
- `strategy_annualized_volatility` / `spy_annualized_volatility`：年化波动率；越高代表收益波动越大。
- `strategy_max_drawdown` / `spy_max_drawdown`：最大回撤；越接近 0 越好（负值绝对值越小越稳）。
- `strategy_sharpe` / `spy_sharpe`：每单位总波动对应的平均收益；越高越好。
- `strategy_sortino`：只惩罚下行波动的风险调整收益；越高越好。
- `strategy_calmar`：年化收益相对最大回撤的效率；越高越好。

分布与尾部风险：

- `strategy_skew` / `spy_skew`：收益分布偏度；负偏度更容易出现大幅负收益尾部。
- `strategy_kurtosis` / `spy_kurtosis`：收益分布峰度；越高通常表示尾部更厚、极端值更多。
- `strategy_var_95` / `spy_var_95`：95% VaR（单期在 95% 置信下的损失分位）；数值越负表示潜在损失更大。
- `strategy_cvar_95` / `spy_cvar_95`：95% CVaR（最差 5% 情况下的平均损失）；更能反映尾部极端风险。

相对基准表现：

- `win_rate_vs_spy`：单期跑赢 SPY 的比例；>50% 代表多数期领先。
- `avg_excess_return_per_period`：单期平均超额收益（策略减 SPY）；正值代表平均每期有超额。
- `tracking_error_annualized`：年化跟踪误差（超额收益波动）；越高代表相对基准偏离更大。
- `information_ratio`：超额收益/跟踪误差（年化口径）；越高表示单位主动风险带来的超额越多。
- `alpha`：对 SPY 回归后的截距；可理解为剔除 beta 暴露后的平均超额。
- `beta`：对 SPY 的系统性暴露；`beta>1` 通常表示比 SPY 更“放大”市场波动。
- `hedged_sharpe`：做 beta 对冲后的夏普；用于看“去市场方向后”的纯策略质量。

交易执行与覆盖度：

- `avg_turnover_per_period`：平均单期换手率；越高成本压力越大。
- `median_turnover_per_period`：单期换手率中位数；比均值更不受极端换手影响。
- `max_turnover_per_period`：单期最大换手率；用于识别最激进换仓期。
- `annualized_turnover`：换手率年化近似；用于与其他策略统一比较交易强度。
- `avg_active_names`：平均活跃标的数；衡量平均持仓覆盖度。
- `median_active_names`：活跃标的数中位数；观察典型持仓宽度。
- `min_active_names`：最少活跃标的数；过低时可能提示组合过度集中。
- `max_active_names`：最多活跃标的数；用于观察覆盖上界。

信号有效性（IC）：

- `ic_mean`：Pearson IC 均值（信号与未来收益线性相关）；正值越大越好。
- `ic_std`：IC 波动；越小通常表示信号稳定性更好。
- `ic_ir`：`ic_mean / ic_std`；可视为 IC 的“夏普”，越高越好。
- `ic_positive_rate`：IC 为正的期数占比；越高表示信号方向一致性更好。
- `rank_ic_mean`：Spearman Rank IC 均值（秩相关）；对非线性单调关系更稳健。
- `rank_ic_std`：Rank IC 波动；越小越稳定。
- `rank_ic_ir`：`rank_ic_mean / rank_ic_std`；越高越好。
- `rank_ic_positive_rate`：Rank IC 为正的期数占比；越高越好。

注：当前 `strategy_nav.csv` / `spy_nav.csv` 序列的首个点是“首个 OOS 评估期结束后的净值”，不是显式起点 `1.0` 基线点。

## 注意事项与当前局限性

- 回测周期的确切时间戳现在使用每个测试切片中真实的最后日期（除非有必要，否则不使用日历上的 `test_end` 作为后备方案）。
- 当前主评估协议是 walk-forward OOS rolling windows（脚本中两个 segment 串接）。
- 两个 segment 串接时若日期重叠，会按时间排序后对重复日期执行“后者覆盖前者”（`keep="last"`，当前实现中通常是 segment B 覆盖）。
- `--tuning-cv-folds > 1` 时会在训练窗口上启用 expanding 时间序列 CV 调参；`=1` 则回退为单验证集调参。
- 启用 holdout 时，脚本会额外输出一套 `holdout/*` 指标；若 holdout 与主回测窗口重叠，会在 `run_summary.txt` 中明确提示。
- holdout 评估时，训练集使用 `holdout_start` 之前的全部历史数据，模型参数/特征来源由 `--holdout-model-segment` 指定；评估分期与主回测一致，按 `--test-months` 聚合后再换仓与计分（默认季度）。
- `active_names`（活跃标的数量）通过统计最终组合中绝对权重大于 0 的不重复股票代码（ticker）得出。
- 换手率是基于标的层面的权重估算得出的；这是一种实用的近似方法，而不是完整的订单级别执行模型。
- 脚本目前使用本地 `src` 路径注入的方式来直接执行 (`scripts/*.py`)。

## 与 Notebook 的差异

- 标签口径不同：脚本默认 `--label-source actual`（`next_period_return - spy_next_period_return`）；Notebook 示例使用 `pred_rel_return` 生成 `rel_performance` 标签。
- 缺失值处理口径不同：脚本按训练窗口拟合填充统计量并应用到验证/测试窗口（降低泄露风险）；Notebook 示例采用全局 `fillna(0)`。
- 特征缩放口径不同：Notebook 多处使用 `MinMaxScaler`；脚本默认不做 `MinMaxScaler`（随机森林对缩放不敏感）。
- 调参与验证协议不同：脚本支持 `--tuning-cv-folds` 的 expanding 时间序列 CV；Notebook 主要是固定验证集上的 Optuna 实验。
- 回测组织方式不同：两者都包含 rolling OOS 评估，但脚本提供标准化、可复现的分段协议与统一产物目录（含 `run_config.json`、`run_summary.txt`）。
- 脚本支持独立 `holdout` OOS（`holdout/*` 一整套输出）；Notebook 默认没有对应的目录化 holdout 产物约定。
- 组合与成本口径不同：脚本按权重、换手率与 `cost_bps` 计成本，并支持 `heuristic` / `signal_risk_qp`；Notebook 主要使用 `pred * return` 形式的收益近似。
