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
  - 先将模型输出映射为连续信号（默认使用 `predict_proba` 的 `P(+1)-P(-1)`）
  - 横截面阈值过滤（`--portfolio-min-score`）+ z-score 截断（`--portfolio-winsor-z`）
  - 可选 train-window 波动率缩放（`--portfolio-vol-scaling` / `--portfolio-vol-power`）
  - 在单票上限（`--portfolio-max-name-weight`）下分配多空权重，并约束总杠杆/净敞口（`--portfolio-gross-target` / `--portfolio-net-target`）
  - 可选粗粒度行业去均值（`--portfolio-sector-neutral`）
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
  - `--portfolio-gross-target`, `--portfolio-net-target`
  - `--portfolio-max-name-weight`, `--portfolio-min-names-per-side`
  - `--portfolio-vol-scaling`, `--portfolio-vol-power`
  - `--portfolio-sector-neutral`, `--portfolio-sector-prefix`
- `--n-trials`：用于随机森林调参的 Optuna 试验次数
- `--tuning-cv-folds`：调参时的时间序列 CV 折数（`1` 表示关闭 CV，使用单验证集）
- `--feature-selection`：特征选择方式（`none` / `importance` / `sequential`）
- `--min-features`：序列特征选择（sequential selection）的特征数量下限
- `--max-selection-steps`：序列特征选择循环的最大步数限制
- `--random-seed`：随机种子
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

- `strategy_total_return`：策略净值区间总收益（`NAV_end / NAV_start - 1`）
- `spy_total_return`：SPY（标普500ETF）净值区间总收益（`NAV_end / NAV_start - 1`）
- 年化与风险：
  - `strategy_annualized_return`, `spy_annualized_return`
  - `strategy_annualized_volatility`, `spy_annualized_volatility`
  - `strategy_max_drawdown`, `spy_max_drawdown`
- `strategy_sharpe`：策略每期收益率的均值/标准差（即夏普比率）
- `spy_sharpe`：SPY每期收益率的均值/标准差
- `strategy_sortino`：Sortino 比率（基于下行波动）
- `strategy_calmar`：Calmar 比率（年化收益 / 最大回撤）
- 分布与尾部风险：
  - `strategy_skew`, `strategy_kurtosis`, `spy_skew`, `spy_kurtosis`
  - `strategy_var_95`, `strategy_cvar_95`, `spy_var_95`, `spy_cvar_95`
- `alpha`, `beta`：策略收益率对 SPY 收益率进行 OLS（普通最小二乘法）回归的截距（alpha）和斜率（beta）
- `information_ratio`：相对 SPY 的超额收益信息比率（`avg_excess_return_per_period / tracking_error`，按期数年化）
- `hedged_sharpe`：Beta对冲后收益率的夏普比率（`strategy_ret - beta * spy_ret`）
- 相对表现：
  - `win_rate_vs_spy`, `avg_excess_return_per_period`, `tracking_error_annualized`
- 执行与覆盖度：
  - `avg_turnover_per_period`, `median_turnover_per_period`, `max_turnover_per_period`, `annualized_turnover`
  - `avg_active_names`, `median_active_names`, `min_active_names`, `max_active_names`
- IC：
  - `ic_mean`, `ic_std`, `ic_ir`, `ic_positive_rate`
  - `rank_ic_mean`, `rank_ic_std`, `rank_ic_ir`, `rank_ic_positive_rate`

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

- 当前模块实现未使用 `MinMaxScaler`；随机森林对特征缩放不敏感，因此默认省略。
- 脚本支持 `--tuning-cv-folds` 的 expanding 时间序列 CV 调参；Notebook 流程通常是单次切分试验。
- 脚本支持独立 `holdout` OOS 评估并输出 `holdout/*` 产物；Notebook 默认没有固定的目录化产物约定。
- 当前项目主目标是可复现回测与风险收益指标输出（`metrics.json` / `run_summary.txt` / OOS 诊断表），不再默认输出 notebook 中的交互绘图与分类报告。
