# A 股日频 Alpha 因子研究框架

本文说明 `money-tree` 如何作为 A 股日频 Alpha101 / Alpha191 / Alpha158 / Alpha360 因子研究底座，并给出 TuShare 数据拉取、因子获取和 XGBoost regressor 回测入口。当前范围只覆盖日频，不考虑小时、分钟或 tick。

## 总体路线

`money-tree` 继续保持轻量回测骨架定位：

```text
TuShare/外部数据
-> 标准 date/ticker 日频 panel
-> 外部 Alpha101/191 或内置 Alpha158/360-style 特征
-> feature_lag_periods=1 防止 T 日特征直接交易 T 日收益
-> xgboost_regressor 预测 rel_return
-> cn market profile 过滤停牌、ST、涨跌停
-> IC / RankIC / 分组或组合回测诊断
```

新增模型入口是 `xgboost_regressor`。它训练连续目标 `rel_return`，也就是：

```text
rel_return = next_period_return - benchmark_next_period_return
```

回测组合仍使用模型输出的连续 score 排序、截面标准化和组合约束。

## 四类 Alpha 是什么

| 系列 | 来源/性质 | 典型输入 | 本仓库支持方式 |
| --- | --- | --- | --- |
| Alpha101 / WQ101 | WorldQuant 101 Formulaic Alphas。DolphinDB 文档说明 `wq101alpha` 函数名为 `WQAlpha1` 到 `WQAlpha101`，输入覆盖 open、high、low、close、vol、vwap、cap、indclass 等。 | OHLCV、VWAP、市值、行业 | 外部生成后并入 panel |
| Alpha191 / GTJA191 | 国泰君安 2017 短周期价量因子库。DolphinDB `gtja191Alpha` 模块实现了 191 个函数。 | OHLCV、VWAP，少数需要指数 open/close | 外部生成后并入 panel |
| Alpha158 | Microsoft Qlib 的工程化日频特征 handler。Qlib 文档把 Alpha158/Alpha360 列为中美市场 off-the-shelf datasets。 | 日频 OHLCV | 内置 Alpha158-style 158 列基线；精确复现建议用 Qlib 生成后并入 |
| Alpha360 | Microsoft Qlib 的序列展开类特征，一般理解为多字段、多 lag 的日频序列输入。 | 日频 OHLCV/VWAP | 内置 6 字段 x 60 lag = 360 列基线 |

参考来源：

- WorldQuant 101 / DolphinDB: <https://docs.dolphindb.com/en/Tutorials/wq101alpha.html>
- GTJA191 / DolphinDB: <https://docs.dolphindb.com/zh/modules/gtja191Alpha/191alpha.html>
- Qlib Alpha158/Alpha360: <https://qlib.readthedocs.io/en/latest/component/data.html>

## 因子清单与口径

本仓库把因子分成“外部公式库并入”和“本地生成基线”两类。文档只维护稳定的列名规则、输入口径和生成方式；完整逐列值以代码或外部生成结果为准，避免手写清单和实现漂移。列级清单见 [factor_catalog.md](factor_catalog.md)，机器可读版本见 [factor_catalog.csv](factor_catalog.csv)。

| 因子/字段组 | 列名规则 | 数量 | 输入口径 | 生成方式 | 说明 |
| --- | --- | ---: | --- | --- | --- |
| Alpha101 / WQ101 | `alpha101_001` 到 `alpha101_101` | 101 | OHLCV、VWAP、市值、行业 | 外部生成后并入 panel | 本仓库不重写公式。行业相关因子必须使用 point-in-time 行业和市值。 |
| Alpha191 / GTJA191 | `alpha191_001` 到 `alpha191_191` | 191 | OHLCV、VWAP，少数需要指数 open/close | 外部生成后并入 panel | 本仓库不重写公式。不同实现的 `SMA`、`DECAYLINEAR` 和缺失值处理需要固定版本。 |
| Alpha158 local baseline | `alpha158_*` | 158 | `open/high/low/close/vwap` 优先使用复权列，`volume` 不复权，`amount` 可选 | `moneytree.factors.qlib.build_alpha158_features` | Qlib-style 工程特征基线，不承诺和 Qlib 原生 handler 逐列完全一致。 |
| Alpha360 local baseline | `alpha360_{field}_lag{00..59}` | 360 | `open/high/low/close/vwap` 优先使用复权列，`volume` 不复权 | `moneytree.factors.qlib.build_alpha360_features` | 6 个字段 x 60 lag。价格类字段按当前 `close` 归一，`volume` 按当前 `volume` 归一。 |
| TuShare daily_basic 派生字段 | `turnover_rate`、`volume_ratio`、`total_mv`、`circ_mv` 等 | 随数据源字段变化 | TuShare `daily_basic` | 数据拉取层并入 panel | 这些是候选模型特征或过滤/诊断字段，不属于 Alpha101/191/158/360 公式家族。 |

### 本地 Alpha158 结构

`alpha158_*` 当前由 4 组特征组成：

| 组别 | 列名示例/规则 | 数量 | 含义 |
| --- | --- | ---: | --- |
| K 线形态 | `alpha158_kmid`、`alpha158_klen`、`alpha158_kup`、`alpha158_klow` 等 | 9 | 单日实体、影线、振幅和收盘相对位置。 |
| 价格相对 lag | `alpha158_open_lag00_rel_close` 到 `alpha158_vwap_lag19_rel_close` | 80 | `open/high/low/vwap` 的 20 日 lag 相对当前 `close` 的偏离。 |
| 滚动窗口特征 | `alpha158_roc_20`、`alpha158_ma_20`、`alpha158_rank_20`、`alpha158_vma_20` 等 | 65 | 使用 5、10、20、30、60 日窗口计算动量、均值、波动、分位、区间位置和成交量/成交额特征。 |
| 杂项价量特征 | `alpha158_vwap_rel_close`、`alpha158_high_low_spread` 等 | 4 | VWAP、日内振幅、收盘相对最高/最低价。 |

默认 `build_alpha158_features(..., adjusted=True)` 会优先使用 `open_adj/high_adj/low_adj/close_adj/vwap_adj`；如果不存在复权列，则退回未复权字段。`volume` 始终使用原始成交量，`amount` 缺失时用 `close * volume` 近似。

### 本地 Alpha360 结构

`alpha360_*` 是固定展开的日频序列特征：

```text
alpha360_open_lag00 ... alpha360_open_lag59
alpha360_high_lag00 ... alpha360_high_lag59
alpha360_low_lag00 ... alpha360_low_lag59
alpha360_close_lag00 ... alpha360_close_lag59
alpha360_vwap_lag00 ... alpha360_vwap_lag59
alpha360_volume_lag00 ... alpha360_volume_lag59
```

其中 `lag00` 表示当日值，`lag59` 表示同一股票向前 59 个交易日的值。价格类字段计算为 `shift(field, lag) / current_close - 1`，成交量字段计算为 `shift(volume, lag) / current_volume - 1`。

### 模型使用边界

所有进入模型的特征还会经过训练配置里的 `feature_lag_periods` 处理。默认 `feature_lag_periods=1`，表示 T 日收盘后已知的因子信号滞后一日使用，避免直接用 T 日特征交易 T 日收益。

## 如何获取因子

### Alpha101

推荐路线是先用 DolphinDB `wq101alpha`、成熟 Python 实现或自研算子层生成因子值，再把结果并入 `money-tree` panel。列名建议：

```text
alpha101_001
alpha101_002
...
alpha101_101
```

注意事项：

- 行业相关因子需要 point-in-time 行业分类和市值。
- VWAP 口径要固定，TuShare 日频可用成交额 / 成交股数近似。
- 不要混用未复权价格、复权收益和另一套复权标签。

### Alpha191

推荐路线同 Alpha101：外部公式实现生成，再并入 panel。列名建议：

```text
alpha191_001
alpha191_002
...
alpha191_191
```

注意事项：

- 少数 GTJA191 公式需要指数 open/close，可从 TuShare `index_daily` 补。
- 不同实现对 `SMA`、`DECAYLINEAR`、停牌缺失、涨跌停处理可能不同，研究时要固定版本和口径。

### Alpha158 / Alpha360

本仓库提供两个本地基线：

```python
from moneytree.factors import build_alpha158_features, build_alpha360_features
```

也可以在 TuShare CLI 拉数据时直接追加：

```bash
uv run moneytree-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily_alpha.parquet \
  --benchmark 000300.SH \
  --factor-family alpha158 \
  --factor-family alpha360
```

这里的 Alpha158 是 `money-tree` 的 Qlib-style 158 列日频 OHLCV 基线，不承诺和 Qlib 源码逐列完全一致。若需要严格复现 Qlib，应直接用 Qlib `Alpha158` / `Alpha360` handler 生成特征，再按 `date, ticker` 并入。

## TuShare 数据支持

安装可选依赖：

```bash
uv sync --dev --extra research
```

Token 会按顺序读取：

```text
显式 --token
环境变量 TUSHARE_TOKEN / TUSHARE_PRO_TOKEN / TS_TOKEN / TUSHARE_API_KEY
.env 文件中的同名变量
```

最小拉取：

```bash
uv run moneytree-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --benchmark 000300.SH
```

增量原始缓存：

- `--cache-dir data/raw/tushare` 会把 `daily`、`daily_basic`、`adj_factor`、`stk_limit`、`suspend_d`
  按 `api_name/trade_date=YYYYMMDD.parquet` 存为 raw parquet。
- 重复或扩大同一时间区间时，已有交易日直接读缓存，只请求缺失交易日。
- `--refresh-cache` 会忽略已有缓存并重写；`--refresh-recent-days N` 会重拉最近 N 个交易日，
  用于覆盖数据源近期回填。
- 缓存目录会维护 `manifest.sqlite`，用于记录 API、交易日、parquet 路径、行数和列信息。
- 最终 panel 仍然每次由 raw `daily + adj_factor + daily_basic + ...` 重建，`close_adj` 和收益列是派生结果。

限制股票池：

```bash
uv run moneytree-tushare \
  --start-date 20200101 \
  --end-date 20241231 \
  --tickers 000001.SZ,600000.SH \
  --output data/cn_sample.parquet
```

TuShare 字段来源：

- `daily`: 未复权日线，输出 open/high/low/close/pre_close/vol/amount；TuShare 文档说明 `vol` 是手、`amount` 是千元，并且停牌期间不提供数据。
- `adj_factor`: 复权因子。
- `daily_basic`: turnover、PE/PB、市值、股本等日频指标。
- `index_daily`: benchmark 指数日线。
- `stk_limit`: 每日涨跌停价格。
- `stock_basic`: 股票基础信息、名称、上市日期、退市日期等。

参考来源：

- TuShare daily: <https://tushare.pro/document/2?doc_id=27>
- TuShare daily_basic: <https://tushare.pro/document/2?doc_id=32>
- TuShare adj_factor: <https://tushare.pro/document/2?doc_id=28>
- TuShare index_daily: <https://tushare.pro/document/2?doc_id=95>
- TuShare stk_limit: <https://tushare.pro/document/2?doc_id=183>
- TuShare stock_basic: <https://tushare.pro/document/2?doc_id=25>

## 标准 panel 契约

TuShare CLI 输出 parquet 使用 `date, ticker` MultiIndex，并尽量生成这些列：

```text
open, high, low, close, pre_close
vol, volume, amount, vwap
adj_factor, open_adj, high_adj, low_adj, close_adj, vwap_adj
return_1d, next_period_return
benchmark_open, benchmark_close, benchmark_return
benchmark_next_period_return, benchmark_cum_ret
up_limit, down_limit, hit_up_limit, hit_down_limit
is_suspended, is_st
total_mv, circ_mv, turnover_rate, volume_ratio
```

VWAP 计算口径：

```text
volume = vol * 100
vwap = amount * 1000 / volume
```

默认 `next_period_return` 使用 `close_adj` 计算；如果没有 `adj_factor`，退回使用未复权 `close`。

## XGBoost Regressor 回测

拉好数据后运行：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha.parquet \
  --output-dir artifacts/xgb-alpha-daily
```

默认 `configs/market/cn.yaml` 会启用这些过滤：

```text
is_suspended
is_st
hit_up_limit
hit_down_limit
```

如果你要只看单因子诊断，可以直接调用：

```python
from moneytree.factors import compute_factor_ic, summarize_factor_ic

ic = compute_factor_ic(frame, ["alpha101_001", "alpha158_kmid"])
summary = summarize_factor_ic(ic)
```

## 工程边界

1. Alpha101/191 的完整公式库没有在本仓库内重写。原因是公式口径、行业中性化、停牌处理和版权边界都需要单独治理；当前更稳的方式是用外部可信实现生成数值，再进入统一 panel。
2. TuShare 拉取层提供研究数据骨架，不自动解决历史 ST、历史行业归属、退市股票完整 universe 和幸存者偏差。
3. 本地 Alpha158/360 是日频 ML 特征基线。若研究目标是“复现 Qlib”，请使用 Qlib 原生 handler 生成。
4. 所有模型特征默认还会被 `feature_lag_periods=1` 再滞后一日，保持 T 日收盘后信号用于下一期的保守约束。
