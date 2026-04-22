# Minimal Run

这个项目的最小工作流只做两件事：先确认主链路能跑，再开始替换或扩展市场实现。

## 1. 安装依赖

```bash
uv sync --dev
```

## 2. 准备一个最小数据文件

如果你走 `us` 路径，数据至少需要满足这些列契约：

- `date`
- `ticker`
- `next_period_return`
- `spy_cum_ret`
- `spy_next_period_return`

如果你走 `cn` 路径，最少还需要：

- `benchmark_cum_ret`
- `benchmark_next_period_return`
- `is_suspended`
- `is_st`
- `hit_up_limit`
- `hit_down_limit`

对应的列名和过滤开关可以在 `configs/market/cn.yaml` 里改。

## 3. 运行 smoke 配置

```bash
uv run moneytree \
  --config configs/market/us.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data ./data_small.parquet \
  --output-dir ./artifacts/smoke
```

## 4. 开始做自己的市场适配

建议顺序：

1. 修改 `configs/market/*.yaml`
2. 只在现有 market profile 不够用时再扩展 `src/treealpha/markets/*.py`
3. 再增加新特征与新模型配置
