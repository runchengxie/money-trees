# 数据契约

本文说明 Money Trees 运行回测时需要的数据形状、必需列、可选列和标签口径。

## 文件格式

`moneytrees` 支持两类输入：

- pickle：`.pkl`、`.pickle`
- parquet：`.parquet`

推荐使用 parquet。pickle 适合迁移旧研究数据，转换脚本：

```bash
uv run python scripts/convert_pickle_to_parquet.py \
  --input data_small.pkl
```

## 索引

标准索引是 `date, ticker`：

```text
date        ticker
2021-01-04 000001.SZ
2021-01-04 600000.SH
2021-01-05 000001.SZ
```

输入文件可以使用普通列：

```text
date, ticker, next_period_return, benchmark_next_period_return, ...
```

运行时会调用 `ensure_date_ticker_index` 转成 MultiIndex，并按 `date, ticker` 排序。

## 最小必需列

`configs/market/cn.yaml` 默认使用 `label_source: actual`。此时最小列包括：

| 列 | 用途 |
| --- | --- |
| `date` | 交易日期，或 MultiIndex 的第一级。 |
| `ticker` | 股票代码，或 MultiIndex 的第二级。 |
| `next_period_return` | 下一期股票收益，用于训练目标和组合收益。 |
| `benchmark_next_period_return` | 下一期基准收益，用于计算相对收益。 |
| `benchmark_cum_ret` | 基准累计收益序列，用于生成基准净值。 |
| `is_suspended` | 停牌过滤。 |
| `is_st` | ST 过滤。 |
| `hit_up_limit` | 涨停过滤。 |
| `hit_down_limit` | 跌停过滤。 |

可交易过滤列只有在配置中开启时才是必需列。默认 `cn` 配置全部开启。

## 标签列

默认标签来源是 `actual`：

```text
rel_return = next_period_return - benchmark_next_period_return
```

分类模型训练目标：

```text
rel_performance = sign_bucket(rel_return, threshold=label_threshold)
```

其中：

- `rel_return > label_threshold` 标为 `1`。
- `rel_return < -label_threshold` 标为 `-1`。
- 其他样本标为 `0`。

回归模型训练目标是 `rel_return`。

`configs/preset/legacy_notebook_compat.yaml` 会切到 `label_source: pred_rel_return`。此时输入文件必须包含：

```text
pred_rel_return
```

该列会直接作为 `rel_return`。

## 特征列选择

模型特征由 `get_feature_columns` 自动识别。规则：

- 只保留数值列和布尔列。
- 排除标签、收益、基准、日期、股票代码和交易状态等保留列。
- 额外排除当前市场配置中的可交易过滤列。

保留列包括：

```text
date
ticker
return
cum_ret
benchmark_cum_ret
benchmark_next_period_return
next_period_return
pred_rel_return
rel_return
rel_performance
is_tradable
tradeable
```

## 特征滞后

默认 `feature_lag_periods=1`。所有模型特征会按 ticker 滞后一行，避免用同一天收盘后才知道的特征直接交易同一天收益。

如果输入数据已经完成严格的特征对齐，可以在配置中设为：

```yaml
market:
  feature_lag_periods: 0
```

Legacy notebook 兼容预设会关闭额外滞后。正式 Alpha101/191/158/360 研究路径不建议关闭默认滞后，除非输入数据已经做过严格 point-in-time 对齐。

## 缺失值处理

预处理顺序：

1. 统一索引。
2. 将 `inf` 和 `-inf` 转为缺失值。
3. 按 ticker 前向填充。
4. 训练、验证和测试切片中使用训练窗口统计量填充。

训练窗口填充规则：

- 数值列用训练窗口中位数。
- 布尔列用 `False`。
- 字符串列用 `"missing"`。
- 可选生成 `__is_missing` 缺失指示列。

## TuShare 标准面板

`moneytrees-tushare` 输出 parquet 会尽量生成以下列：

```text
open, high, low, close, pre_close
vol, volume, amount, vwap
adj_factor, open_adj, high_adj, low_adj, close_adj, vwap_adj
return_1d, next_period_return
benchmark_open, benchmark_close, benchmark_high, benchmark_low
benchmark_return, benchmark_next_period_return, benchmark_cum_ret
up_limit, down_limit, hit_up_limit, hit_down_limit
is_suspended, is_st
total_mv, circ_mv, turnover_rate, turnover_rate_f, volume_ratio
pe, pe_ttm, pb, ps, ps_ttm, dv_ratio, dv_ttm
total_share, float_share, free_share
name, industry, list_date, delist_date, listed_days
```

实际列取决于 TuShare 权限、命令行跳过参数和接口返回。

## VWAP 与复权口径

TuShare `daily` 中：

- `vol` 单位是手。
- `amount` 单位是千元。

项目换算：

```text
volume = vol * 100
vwap = amount * 1000 / volume
```

存在 `adj_factor` 时会生成：

```text
open_adj, high_adj, low_adj, close_adj, vwap_adj
```

`next_period_return` 优先使用 `close_adj` 计算，缺少复权列时使用未复权 `close`。

## 常见错误

- 缺 `benchmark_next_period_return`：默认标签来源需要它计算相对收益。
- 缺 `benchmark_cum_ret`：无法生成基准净值。
- 开启 ST 或停牌过滤但缺对应列：`cn` 市场配置档会立即报错。
- 使用 legacy notebook 兼容预设但缺 `pred_rel_return`：该预设依赖外部预测收益列。
- 特征滞后后样本为空：检查每只股票是否至少有两期特征数据。
