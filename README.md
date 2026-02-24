# 截面随机森林

基于脚本且具备可复现回测流程的截面随机森林策略研究项目。

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

## 策略定义与假设

- 标签来源：
  - `actual`（默认）：`next_period_return - spy_next_period_return`（超额收益）
  - `pred_rel_return`：使用预先计算好的 `pred_rel_return`
- 标签映射（`--label-threshold`，默认值为 `0.05`）：
  - `> 阈值 -> +1`
  - `< 负阈值 -> -1`
  - 其他情况 `-> 0`
- 仓位管理：
  - 对预测值非零的标的进行等权重的做多/做空
  - 预测值为零意味着不持有仓位
- 交易成本：
  - 换手率（turnover）估算方式为：
    - `0.5 * sum_i |w_t,i - w_(t-1),i|`
  - 每期扣除的成本为 `turnover * cost_bps / 10000`

## 数据泄露处理

缺失值的中位数填充，现在会在每个训练窗口（train window）上进行拟合，然后再应用到验证/测试窗口（valid/test windows）中。

处理流程：

1. 全局安全步骤：无穷大值（inf）替换为 NaN、按股票代码前向填充（forward-fill）、标签构建
2. 逐窗口拟合/转换（fit/transform）：
   - 在训练数据切片上拟合计算中位数
   - 将训练集计算出的中位数应用到训练/验证/测试数据切片上

这避免了使用全局中位数导致用到未来数据（即数据泄露）。

## 运行回测

```bash
uv run python scripts/run_backtest.py \
  --data data_small.pkl \
  --output-dir artifacts/backtest \
  --feature-selection importance \
  --n-trials 50 \
  --cost-bps 10
```

## 主要参数

- `--data`：输入的 `.pkl`/`.parquet` 文件路径
- `--output-dir`：输出文件夹
- `--label-source`：`actual` 或 `pred_rel_return`
- `--label-threshold`：标签划分阈值
- `--add-missing-indicators`：添加 `__is_missing` 数值型指示变量（标志缺失值）
- `--cost-bps`：以基点（bps）为单位的交易成本
- `--n-trials`：用于随机森林调参的 Optuna 试验次数
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
- `--export-parquet`：保存全局预处理后 parquet 文件的可选路径

## 输出结果

- `strategy_nav.csv`
- `spy_nav.csv`
- `strategy_returns.csv`
- `spy_returns.csv`
- `strategy_vs_spy.csv`
- `metrics.json`
- `segment_a_features.txt`
- `segment_b_features.txt`
- 可选的特征选择历史记录：
  - `segment_a_selection_history.csv`
  - `segment_b_selection_history.csv`

## 指标定义 (`metrics.json`)

- `strategy_total_return`：策略最终净值（NAV）减去 1
- `spy_total_return`：SPY（标普500ETF）最终净值减去 1
- `strategy_sharpe`：策略每期收益率的均值/标准差（即夏普比率）
- `spy_sharpe`：SPY每期收益率的均值/标准差
- `alpha`, `beta`：策略收益率对 SPY 收益率进行 OLS（普通最小二乘法）回归的截距（alpha）和斜率（beta）
- `information_ratio`：回归残差收益率的均值/标准差（信息比率）
- `hedged_sharpe`：Beta对冲后收益率的夏普比率（`strategy_ret - beta * spy_ret`）

## 注意事项与当前局限性

- 回测周期的确切时间戳现在使用每个测试切片中真实的最后日期（除非有必要，否则不使用日历上的 `test_end` 作为后备方案）。
- `active_names`（活跃标的数量）通过统计具有非零信号的不重复股票代码（ticker）得出。
- 换手率是基于标的层面的权重估算得出的；这是一种实用的近似方法，而不是完整的订单级别执行模型。
- 脚本目前使用本地 `src` 路径注入的方式来直接执行 (`scripts/*.py`)。

## 将 pickle 转换为 parquet

```bash
uv run python scripts/convert_pickle_to_parquet.py --input data_small.pkl
```
