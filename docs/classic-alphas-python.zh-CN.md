# 用纯 Python 生成 Alpha101/191

[English page](classic-alphas-python.md)

本文说明如何使用 Money Trees 内置的纯 Python Alpha101/191 生成器。该实现移植自 `wu-alpha191-alpha101` 参考仓库，但把 `rank`、`scale` 改为横截面语义（按交易日分组），滚动算子仍按股票时间序列计算。

## 背景

- 早期参考仓库 `wu-alpha191-alpha101` 提供逐股票的 Alpha191/Alpha101 Python 实现，但 `rank`/`scale` 用的是单只股票时间序列排名，与标准定义（横截面排名）不一致。
- Money Trees 的 `src/moneytree/factors/classic.py` 把公式移植到标准 `date, ticker` 面板上，`rank`/`scale` 按交易日横截面计算，`ts_*` 滚动算子按股票分组。
- 参考仓库 `wu-alpha191-alpha101` 的 README 已标注本仓库为取代者。公式来自公开研报和论文，迁移时保留了结构，只修正了口径。

## 支持的字段

| 字段 | 来源列（优先复权，`--raw-price-fields` 时用未复权） | 说明 |
| --- | --- | --- |
| `open` / `high` / `low` / `close` | `open_adj` / `high_adj` / `low_adj` / `close_adj`，缺省退回 `open` 等 | 价格类字段。 |
| `vwap` | `vwap_adj`，缺省退回 `vwap` | 成交量加权均价。 |
| `volume` | `volume` | 原始成交量（股）。 |
| `returns` | 由 `close` 按股票计算 `pct_change` | 收益序列。 |
| `turnover` | `amount` | 成交额。 |
| `turnover_rate` | `turnover_rate` | 换手率，缺失时该因子输出缺失。 |
| `cap` | `circ_mv`，缺省退回 `total_mv` | 市值。 |
| `industry` | `industry` | 行业。 |

`index_open` / `index_close`（`benchmark_open` / `benchmark_close`）保留在上下文里，当前移植的公式未使用。

## Python 调用

```python
import pandas as pd
from moneytree.factors import build_alpha101_features, build_alpha191_features

panel = pd.read_parquet("data/cn_daily.parquet")
alpha101 = build_alpha101_features(panel)
alpha191 = build_alpha191_features(panel)
```

返回按 `(date, ticker)` 索引的 DataFrame，列名为 `alpha101_001`…`alpha101_101` 和 `alpha191_001`…`alpha191_191`，默认 `float32`。

## CLI 用法

写入兼容宽面板：

```bash
uv run moneytrees-alpha101-191-python \
  --input data/panel/cn/cn_daily_raw.parquet \
  --output data/panel/cn/cn_daily_alpha.parquet \
  --alpha101 \
  --alpha191
```

写入因子仓库：

```bash
uv run moneytrees-alpha101-191-python \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn_daily \
  --no-wide-output \
  --alpha101 \
  --alpha191
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--family` / `--alpha101` / `--alpha191` | 选择因子族。 |
| `--raw-price-fields` | 使用未复权价格字段。 |
| `--factor-dtype` | `float32`（默认）或 `float64`。 |
| `--compression` / `--compression-level` / `--row-group-size` | parquet 写入参数。 |
| `--chunk-trade-dates` | 因子仓库分片交易日数量。 |
| `--overwrite` | 已存在同名因子族时强制重算。 |
| `--progress` | 输出逐因子计算和分片写入进度。 |

## 与 DolphinDB 路径的差异

- 横截面语义：本地实现按交易日分组做 `rank`/`scale`。DolphinDB 模块也按截面处理，但两者的缺失值填充、`SMA`/`DECAYLINEAR` 边界和复权口径可能不同。
- 输入：本地实现直接读取标准面板。DolphinDB 路径上传 `tradetime/securityid` 表。
- 资源：本地实现会一次性在内存中计算全部请求因子。全市场多年面板内存紧张时，建议分因子族、分时间窗口运行，或继续使用 DolphinDB 流式路径（`--stream-input auto`）。
- 建议：正式全量生成前，先抽几个因子和 DolphinDB 输出做小样本对拍，确认口径后再推广。

## 计算资源提示

滚动 `ts_rank`、`decay_linear`、`ts_argmax` 等算子使用逐股票 `rolling.apply`，在非常大的面板上较慢。可以用 `--progress` 观察进度。需要极大规模生产时优先考虑 DolphinDB 路径或并行分窗。
