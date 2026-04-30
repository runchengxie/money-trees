# 输出产物

默认输出目录由 `--output-dir` 或 `output.output_dir` 控制。一次正常回测会写出策略净值、基准净值、信号诊断、指标、运行配置和报告数据。

## 核心文件

| 文件 | 内容 |
| --- | --- |
| `metrics.json` | 策略、基准、风险、换手、持仓数、IC 和 RankIC 指标。 |
| `run_config.json` | 解析后的配置、基准净值口径、segment 规格、segment fit 元数据、holdout 信息、运行时间和 git commit。 |
| `experiment_manifest.json` | 可复现实验元数据，包括输入 hash、schema hash、配置 hash、运行环境和数据版本。 |
| `run_summary.txt` | 面向人工阅读的回测摘要。 |
| `segment_a_features.txt` | Segment A 最终使用的特征列。 |
| `segment_b_features.txt` | Segment B 最终使用的特征列。 |

## 净值和收益

| 文件 | 内容 |
| --- | --- |
| `strategy_nav.csv` | 组合权重回测净值。 |
| `signal_nav.csv` | 基于离散信号的诊断净值。 |
| `benchmark_nav.csv` | 基准净值，对齐策略评估日期。 |
| `strategy_returns.csv` | 策略分期收益。 |
| `benchmark_returns.csv` | 基准分期收益。 |
| `strategy_vs_benchmark.csv` | 策略和基准净值合并表。 |

## 诊断文件

| 文件 | 内容 |
| --- | --- |
| `signal_profit.csv` | 信号收益、信号换手和信号活跃股票数。 |
| `strategy_turnover.csv` | 策略换手。 |
| `active_names.csv` | 每期组合持仓数量。 |
| `ic_series.csv` | 每期 IC 和 RankIC。 |
| `oos_period_diagnostics.csv` | 样本外分期收益、换手、持仓数、信号收益、IC、RankIC、目标/实际暴露、未分配暴露和 QP fallback 状态。 |

## Notebook 报告数据

| 文件 | 内容 |
| --- | --- |
| `notebook_report_navs.csv` | 策略、基准、信号和可选对冲净值。 |
| `notebook_rolling_beta.csv` | 滚动 beta。 |
| `notebook_residual_returns.csv` | 回归残差收益。 |
| `notebook_residual_distribution.csv` | 残差分布直方图数据。 |

## 特征选择产物

以下文件只在特征选择历史存在时输出：

| 文件 | 内容 |
| --- | --- |
| `segment_a_selection_history.csv` | Segment A 特征选择历史。 |
| `segment_b_selection_history.csv` | Segment B 特征选择历史。 |
| `segment_a_feature_score_curve.csv` | Segment A 特征数和验证收益曲线。 |
| `segment_b_feature_score_curve.csv` | Segment B 特征数和验证收益曲线。 |

## Holdout 子目录

配置 `backtest.holdout.start` 和 `backtest.holdout.end` 后，会生成 `holdout/` 子目录。

`holdout/` 包含：

- `strategy_nav.csv`
- `signal_nav.csv`
- `benchmark_nav.csv`
- `strategy_returns.csv`
- `benchmark_returns.csv`
- `signal_profit.csv`
- `strategy_turnover.csv`
- `active_names.csv`
- `ic_series.csv`
- `oos_period_diagnostics.csv`
- `strategy_vs_benchmark.csv`
- `notebook_report_navs.csv`
- `notebook_rolling_beta.csv`
- `notebook_residual_returns.csv`
- `notebook_residual_distribution.csv`
- `metrics.json`
- `holdout_config.json`

`holdout_config.json` 记录 holdout 使用的模型 segment、训练区间、验证区间和基准名称。

## `metrics.json` 指标

主要指标包括：

- 总收益和年化收益。
- 年化波动、最大回撤、Sharpe、Sortino、Calmar。
- VaR 95% 和 CVaR 95%。
- 相对基准胜率、平均超额收益、年化 tracking error、information ratio。
- Alpha、Beta 和 hedged Sharpe。
- 平均、最大和年化换手。
- 平均、最小和最大持仓数。
- IC、RankIC 的均值、标准差、IR 和正值比例。
- Segment A/B 的验证收益、验证换手、特征数和调参最优值。

## `run_config.json` 元数据

当前记录：

- `resolved_at_utc`
- `git_commit`
- `output_schema_version`
- CLI 和配置解析后的参数。
- 基准名称、基准列和 `benchmark_cum_mode`。
- Segment A/B 的训练、验证和滚动回测规格。
- Segment A/B 的模型 ID、验证区间、特征数、调参状态和调参最优值。
- Holdout 是否开启及其区间。
- `reproducibility` 摘要，包括 `dataset_version`、输入文件 hash、schema hash、配置 hash 和 `experiment_manifest.json` 自身 hash。

## `experiment_manifest.json`

该文件用于复现实验，当前包含：

- `manifest_schema_version`
- `output_schema_version`
- 运行时间、git commit、随机种子和输出目录。
- `dataset_version`，由输入文件 SHA-256 和 raw 输入 schema hash 派生。
- 输入数据路径、文件大小、修改时间和 SHA-256。
- raw 输入面板和模型输入面板的行数、列数、日期范围、ticker 数量、schema 和 schema hash。
- 配置文件路径、文件 SHA-256、配置文件集合 hash 和解析后配置 hash。
- 模型 ID、训练目标列和模型参数。
- 市场配置摘要。
- Python、平台和关键依赖包版本。

后续仍可补充输出文件 hash、TuShare raw cache manifest 版本和外部数据源版本。
