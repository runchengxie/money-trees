# A 股日频 Alpha 因子研究

本文说明 Money Trees 当前如何承接 A 股日频 Alpha101、Alpha191、Alpha158 和 Alpha360 研究。数据契约见 [data_contract.md](data_contract.md)，TuShare 拉取示例见 [cookbook.md](cookbook.md)，运行排障见 [runbook.md](runbook.md)。

## 研究链路

```text
TuShare / 外部日频数据
-> 标准 date,ticker 面板
-> 外部 Alpha101/191 或本地 Alpha158/360 特征
-> feature_lag_periods 控制特征可见时间
-> 分类或回归模型生成 score
-> cn 市场配置档做可交易过滤
-> 组合构建、滚动回测、holdout 和报告输出
```

`xgboost_regressor` 和线性模型训练连续目标：

```text
rel_return = next_period_return - benchmark_next_period_return
```

随机森林和 XGBoost 分类模型训练离散目标：

```text
rel_performance in {-1, 0, 1}
```

组合层统一使用模型输出 score 排序、截面标准化和组合约束。

## 因子家族

| 系列 | 来源/性质 | 典型输入 | 本仓库支持方式 |
| --- | --- | --- | --- |
| Alpha101 / WQ101 | WorldQuant 101 Formulaic Alphas。 | OHLCV、VWAP、市值、行业 | 外部生成后并入面板。 |
| Alpha191 / GTJA191 | 国泰君安 191 个短周期价量因子。 | OHLCV、VWAP，少数需要指数 open/close | 外部生成后并入面板。 |
| Alpha158 | Qlib 工程化日频特征 handler。 | 日频 OHLCV/VWAP | 内置 Alpha158-style 158 列基线。 |
| Alpha360 | Qlib 序列展开类日频特征。 | 日频 OHLCV/VWAP | 内置 6 字段 x 60 lag = 360 列基线。 |

参考来源：

- WorldQuant 101 / DolphinDB: <https://docs.dolphindb.com/en/Tutorials/wq101alpha.html>
- GTJA191 / DolphinDB: <https://docs.dolphindb.com/zh/modules/gtja191Alpha/191alpha.html>
- Qlib Alpha158/Alpha360: <https://qlib.readthedocs.io/en/latest/component/data.html>

## 列名和清单

机器可读清单见 [factor_catalog.csv](factor_catalog.csv)，说明文档见 [factor_catalog.md](factor_catalog.md)。CSV 面向人类阅读，包含 `formula_status`、`formula_source` 和 `formula_or_rule`；Alpha158/360 行给出本地公式，Alpha101/191 行标明外部公式未内置。

| 因子/字段组 | 列名规则 | 数量 | 输入口径 | 生成方式 |
| --- | --- | ---: | --- | --- |
| Alpha101 / WQ101 | `alpha101_001` 到 `alpha101_101` | 101 | OHLCV、VWAP、市值、行业 | 外部生成后并入面板。 |
| Alpha191 / GTJA191 | `alpha191_001` 到 `alpha191_191` | 191 | OHLCV、VWAP，少数需要指数 open/close | 外部生成后并入面板。 |
| Alpha158 local baseline | `alpha158_*` | 158 | `open/high/low/close/vwap` 优先复权，`volume` 不复权，`amount` 可选 | `build_alpha158_features` |
| Alpha360 local baseline | `alpha360_{field}_lag{00..59}` | 360 | `open/high/low/close/vwap` 优先复权，`volume` 不复权 | `build_alpha360_features` |
| TuShare `daily_basic` 派生字段 | `turnover_rate`、`volume_ratio`、`total_mv`、`circ_mv` 等 | 随接口返回变化 | TuShare `daily_basic` | 数据拉取层并入面板。 |

Alpha101/191 的公式实现由上游系统维护。研究时要固定行业、市值、VWAP、停牌、涨跌停、缺失值和复权口径。

## 本地 Alpha158

`alpha158_*` 当前由 4 组特征组成：

| 组别 | 列名示例/规则 | 数量 | 含义 |
| --- | --- | ---: | --- |
| K 线形态 | `alpha158_kmid`、`alpha158_klen`、`alpha158_kup`、`alpha158_klow` | 9 | 单日实体、影线、振幅和收盘相对位置。 |
| 价格相对 lag | `alpha158_open_lag00_rel_close` 到 `alpha158_vwap_lag19_rel_close` | 80 | `open/high/low/vwap` 的 20 日 lag 相对当前 `close` 的偏离。 |
| 滚动窗口特征 | `alpha158_roc_20`、`alpha158_ma_20`、`alpha158_rank_20`、`alpha158_vma_20` | 65 | 动量、均值、波动、分位、区间位置和成交量/成交额特征。 |
| 杂项价量特征 | `alpha158_vwap_rel_close`、`alpha158_high_low_spread` | 4 | VWAP、日内振幅、收盘相对最高/最低价。 |

默认 `adjusted=True`：

- 价格类字段优先使用 `open_adj/high_adj/low_adj/close_adj/vwap_adj`。
- 缺少复权列时退回 `open/high/low/close/vwap`。
- `volume` 始终使用原始成交量。
- `amount` 缺失时使用 `close * volume` 近似。

## 本地 Alpha360

`alpha360_*` 是固定展开的日频序列特征：

```text
alpha360_open_lag00 ... alpha360_open_lag59
alpha360_high_lag00 ... alpha360_high_lag59
alpha360_low_lag00 ... alpha360_low_lag59
alpha360_close_lag00 ... alpha360_close_lag59
alpha360_vwap_lag00 ... alpha360_vwap_lag59
alpha360_volume_lag00 ... alpha360_volume_lag59
```

含义：

- `lag00` 表示当日值。
- `lag59` 表示同一股票向前 59 个交易日的值。
- 价格类字段计算为 `shift(field, lag) / current_close - 1`。
- 成交量字段计算为 `shift(volume, lag) / current_volume - 1`。

## 使用方式

在 Python 中生成本地因子：

```python
import pandas as pd
from moneytree.factors import build_alpha158_features, build_alpha360_features

panel = pd.read_parquet("data/cn_daily.parquet")
alpha158 = build_alpha158_features(panel)
alpha360 = build_alpha360_features(panel)
```

在 TuShare CLI 中追加：

```bash
uv run moneytrees-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily_alpha158_360.parquet \
  --benchmark 000300.SH \
  --factor-family alpha158 \
  --factor-family alpha360
```

运行 XGBoost 回归：

```bash
uv sync --dev --extra research

uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha158_360.parquet \
  --output-dir artifacts/xgb-alpha-daily
```

## 单因子诊断

```python
import pandas as pd
from moneytree.factors import compute_factor_ic, summarize_factor_ic

frame = pd.read_parquet("data/cn_daily_alpha.parquet")
ic = compute_factor_ic(frame, ["alpha158_kmid", "alpha158_roc_20"])
summary = summarize_factor_ic(ic)
print(summary)
```

默认按日期计算截面 IC 和 RankIC，收益列为 `next_period_return`。

## 研究边界

- Alpha101/191 的公式值由外部实现生成，接入前需要固定上游版本和字段口径。
- TuShare 拉取层提供研究数据骨架，历史 ST、历史行业归属、退市股票完整样本和幸存者偏差需要上游治理。
- 本地 Alpha158/360 是日频 ML 特征基线；严格复现 Qlib 时应使用 Qlib 原生 handler 生成特征。
- 默认 `feature_lag_periods=1`，表示 T 日收盘后可见的特征信号滞后一日使用。
