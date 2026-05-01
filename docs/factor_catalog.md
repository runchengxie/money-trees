# 因子列级清单

本页说明完整列级清单的使用方式。机器可读清单见 [factor_catalog.csv](factor_catalog.csv)，生成脚本见 `project_tools/generate_factor_catalog.py`。

## 覆盖范围

| 因子家族 | 行数 | 维护方式 |
| --- | ---: | --- |
| Alpha101 / WQ101 | 101 | 标准列名、输入依赖和外部并入口径；逐条公式未内置。 |
| Alpha191 / GTJA191 | 191 | 标准列名、输入依赖和外部并入口径；逐条公式未内置。 |
| Alpha158 local baseline | 158 | 与 `moneytree.factors.qlib.build_alpha158_features` 当前实现对齐，每行包含本地公式。 |
| Alpha360 local baseline | 360 | 与 `moneytree.factors.qlib.build_alpha360_features` 当前实现对齐，每行包含本地公式。 |

合计 810 行。Alpha101/191 的逐条公式不由 Python 本地因子函数维护；CSV 中对应行是 DolphinDB 外部生成路径的接入清单。

当前项目内可计算 Alpha158/360 共 518 个本地特征。Alpha101/191 共 292 个列由 DolphinDB 外部生成路径生成；本仓库包含 `docker/dolphindb/modules/` 下的模块和 Money Trees 包装模块，并维护标准列名、输入依赖、校验规则和并入口径。`add_factor_family_features()` 支持本地 Alpha158/360。推荐将外部 Alpha101/191 写入标准 `date, ticker` 面板或因子仓库，流程见 [generate_alpha101_191_with_dolphindb.md](generate_alpha101_191_with_dolphindb.md)。

## CSV 字段

| 字段 | 说明 |
| --- | --- |
| `family` | 因子家族：`alpha101`、`alpha191`、`alpha158`、`alpha360`。 |
| `column` | 面板中建议或实际使用的列名。 |
| `group` | 粗分组，例如 `external_formula`、`candlestick`、`momentum`、`sequence_lag`。 |
| `count_scope` | 该家族的列数，用于快速核对完整性。 |
| `input_fields` | 该列依赖的核心输入字段。 |
| `formula_status` | `implemented_local` 或 `external_dolphindb_module`。 |
| `formula_source` | 公式来源或接入来源。 |
| `formula_or_rule` | 本地因子的计算规则，或外部因子的接入说明。 |
| `generation` | `external` 或本仓库内置生成函数。 |
| `notes` | 复权、归一化、缺失值或上游实现注意事项。 |

## 口径说明

本地 Alpha158/360 默认 `adjusted=True`，价格类字段优先使用 `open_adj/high_adj/low_adj/close_adj/vwap_adj`，没有复权列时退回未复权字段。`volume` 始终使用原始成交量。

Alpha101/191 行的 `formula_status` 是 `external_dolphindb_module`。这些行的 `formula_or_rule` 说明如何通过 DolphinDB 外部生成路径把值并入面板；Python 核心包不维护对应逐条公式函数。生产使用前应确认模块来源、授权和版本，并在生成命令中记录 module version。

如果要把 Alpha101/191 的逐条公式也作为独立说明放进 CSV，需要先选定公式来源和授权口径，然后把 `formula_status` 改成类似 `documented_external_formula`，并在 `formula_source` 中记录具体来源和版本。

Alpha158 的 `amount_ma_*` 依赖 `amount`；如果面板没有 `amount`，实现会用 `close * volume` 近似。Alpha360 的价格类 lag 使用 `shift(field, lag) / current_close - 1`，成交量 lag 使用 `shift(volume, lag) / current_volume - 1`。

所有进入模型的特征仍受训练配置里的 `feature_lag_periods` 约束。默认 `feature_lag_periods=1`，表示 T 日收盘后可见的因子信号滞后一日使用。
