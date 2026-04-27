# 配置说明

`moneytree` 使用多个 YAML、JSON 或 TOML 配置文件叠加生成一次运行配置。推荐把市场、模型、回测和本地预设拆开维护。

## 默认配置栈

不传 `--config` 时，CLI 默认读取：

```text
configs/market/cn.yaml
configs/model/rf.yaml
configs/backtest/default.yaml
```

等价命令：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --data data_small.parquet \
  --output-dir artifacts/backtest
```

## 合并规则

配置文件按传入顺序深合并：

- 后传入的文件覆盖前面文件的同名字段。
- 字典字段递归合并。
- 非字典字段直接替换。
- `--data` 覆盖配置里的数据路径。
- `--output-dir` 覆盖配置里的输出目录。
- `--set dotted.path=value` 覆盖最终配置。

示例：

```bash
uv run moneytree \
  --data data_small.parquet \
  --output-dir artifacts/debug \
  --set model.n_trials=0 \
  --set model.feature_selection=none \
  --set backtest.segment1_windows=1 \
  --set backtest.segment2_windows=1
```

`--set` 会自动解析布尔值、整数、浮点数和 JSON 字面量。

## 市场配置

文件：`configs/market/cn.yaml`

核心字段：

```yaml
market:
  profile: cn
  benchmark: 000300.SH
  benchmark_return_column: benchmark_next_period_return
  benchmark_cum_column: benchmark_cum_ret
  label_source: actual
  label_threshold: 0.03
  feature_lag_periods: 1
  add_missing_indicators: false
  tradability_columns:
    suspend: is_suspended
    st: is_st
    up_limit: hit_up_limit
    down_limit: hit_down_limit
  tradability_filters:
    suspend: true
    st: true
    up_limit: true
    down_limit: true
```

说明：

- `profile` 当前只支持 `cn`。
- `benchmark_return_column` 和 `benchmark_cum_column` 可以映射上游不同列名。
- `label_source: actual` 使用真实相对收益生成标签。
- `label_source: pred_rel_return` 使用输入数据中的 `pred_rel_return`。
- `feature_lag_periods` 控制模型特征按 ticker 滞后多少期。

## 模型配置

文件目录：`configs/model/`

内置配置：

| 文件 | 模型 ID | 训练目标 | 说明 |
| --- | --- | --- | --- |
| `rf.yaml` | `random_forest` | `rel_performance` | 分类主路径，支持调参和特征选择。 |
| `xgb.yaml` | `xgboost` | `rel_performance` | XGBoost 分类，依赖 `xgboost` extra。 |
| `xgb_regressor.yaml` | `xgboost_regressor` | `rel_return` | XGBoost 回归，依赖 `xgboost` extra。 |
| `ridge.yaml` | `ridge` | `rel_return` | 线性回归基准。 |
| `lasso.yaml` | `lasso` | `rel_return` | L1 线性回归基准。 |
| `elasticnet.yaml` | `elasticnet` | `rel_return` | ElasticNet 线性回归基准。 |

通用字段：

```yaml
model:
  id: random_forest
  params:
    n_estimators: 300
  feature_selection: importance
  min_features: 2
  max_selection_steps: 200
  n_trials: 25
  tuning_cv_folds: 3
  random_seed: 123
```

模型适配器会校验自己支持的调参和特征选择能力。线性模型和 XGBoost 当前只支持 `feature_selection: none`，随机森林支持 `none`、`importance`、`sequential` 和 `notebook_compat`。

## 组合配置

文件：`configs/backtest/default.yaml`

组合字段位于 `portfolio`：

```yaml
portfolio:
  min_score: 0.05
  winsor_z: 3.0
  weighting_method: heuristic
  gross_target: 1.0
  net_target: 0.0
  max_name_weight: 0.02
  min_names_per_side: 5
  use_vol_scaling: true
  sector_neutral: false
```

`weighting_method` 支持：

- `heuristic`: 默认启发式权重。
- `signal_risk_qp`: 使用信号、协方差和换手惩罚求解二次规划。

`signal_risk_qp` 的相关字段以 `qp_` 开头，包括风险厌恶、换手惩罚、协方差窗口、收缩估计、候选股票数和求解器参数。

## 回测配置

回测字段位于 `backtest`：

```yaml
backtest:
  cost_bps: 10.0
  train_months: 60
  gap_months: 3
  test_months: 3
  segment1_start: "2004-04-01"
  segment1_windows: 60
  segment2_start: "2009-04-01"
  segment2_windows: 20
  holdout:
    start: ""
    end: ""
    model_segment: segment_b
```

说明：

- `train_months`、`gap_months`、`test_months` 控制滚动窗口形状。
- `segment1_windows` 和 `segment2_windows` 控制两个 segment 的滚动窗口数量。
- holdout 需要同时设置 `start` 和 `end`。
- `model_segment` 可以设为 `segment_a` 或 `segment_b`。

## 输出配置

输出字段位于 `output`：

```yaml
output:
  output_dir: artifacts/backtest
  export_parquet: ""
```

说明：

- `output_dir` 是产物目录。
- `export_parquet` 非空时，会额外保存经过预处理、填充和特征滞后的面板。

## 预设配置

文件目录：`configs/preset/`

当前预设：

- `template_smoke.yaml`: 写入本地 `data_path` 和 `output_dir`，方便本地 smoke 运行。
- `notebook_compat.yaml`: 使用 `pred_rel_return`、关闭特征滞后、切换到 notebook 兼容的随机森林调参和特征选择路径。

预设应放在配置列表最后，让它覆盖前面的基础配置。
