# 冒烟测试

本文给出最小本地回测路径，用来确认 A 股主链路可以跑通。完整数据契约见 [data_contract.md](data_contract.md)，常见研究任务见 [cookbook.md](cookbook.md)。

## 1. 安装依赖

```bash
uv sync --dev
```

## 2. 准备最小数据文件

推荐保存为 parquet：

```text
data_small.parquet
```

最小列：

- `date`
- `ticker`
- `next_period_return`
- `benchmark_next_period_return`
- `benchmark_cum_ret`
- `is_suspended`
- `is_st`
- `hit_up_limit`
- `hit_down_limit`

还需要至少一个数值或布尔特征列，例如：

```text
f_signal
```

默认配置会把 `date,ticker` 转成 MultiIndex，生成 `rel_return` 和 `rel_performance`，再用模型训练。

## 3. 运行 smoke 配置

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data ./data_small.parquet \
  --output-dir ./artifacts/smoke
```

成功后应看到：

```text
artifacts/smoke/metrics.json
artifacts/smoke/run_config.json
artifacts/smoke/experiment_manifest.json
artifacts/smoke/run_summary.txt
artifacts/smoke/strategy_nav.csv
artifacts/smoke/benchmark_nav.csv
artifacts/smoke/holdout/metrics.json
```

## 4. 使用模板预设

`configs/preset/template_smoke.yaml` 内置了本地数据路径和输出目录：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --config configs/preset/template_smoke.yaml
```

该预设默认读取：

```text
./data_small.parquet
```

并输出到：

```text
./artifacts/template-smoke
```

## 5. Notebook 兼容预设

如果输入数据已经包含外部生成的 `pred_rel_return`，可以使用：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --config configs/preset/legacy_notebook_compat.yaml \
  --data ./data_small.parquet \
  --output-dir ./artifacts/notebook-compat
```

这个预设会使用 `pred_rel_return` 作为标签来源，并关闭额外特征滞后。

## 6. 常见失败

- 缺 `benchmark_next_period_return`：默认标签来源需要它计算 `rel_return`。
- 缺 `benchmark_cum_ret`：无法生成基准净值。
- 缺 `is_suspended`、`is_st`、`hit_up_limit` 或 `hit_down_limit`：默认 `cn` 配置开启了可交易过滤。
- 缺特征列：模型没有可训练输入。
- 样本为空：检查日期范围、过滤列和 `feature_lag_periods`。

## 7. 下一步

建议顺序：

1. 按你的上游数据修改 `configs/market/cn.yaml`。
2. 确认 [data_contract.md](data_contract.md) 的必需列都存在。
3. 用 [cookbook.md](cookbook.md) 里的任务示例扩展数据、因子和模型。
4. 按 [runbook.md](runbook.md) 做缓存、排障和归档检查。
