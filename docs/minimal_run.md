# Minimal Run

这个项目的最小工作流只做两件事：先确认 A 股主链路能跑，再开始替换或扩展数据契约。

## 1. 安装依赖

```bash
uv sync --dev
```

## 2. 准备一个最小数据文件

数据至少需要满足这些列契约：

- `date`
- `ticker`
- `next_period_return`
- `benchmark_cum_ret`
- `benchmark_next_period_return`
- `is_suspended`
- `is_st`
- `hit_up_limit`
- `hit_down_limit`

对应的 benchmark 列名和过滤开关可以在 `configs/market/cn.yaml` 里改。

## 3. 运行 smoke 配置

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data ./data_small.parquet \
  --output-dir ./artifacts/smoke
```

如果想用模板 preset 管理本地数据路径和输出目录：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --config configs/preset/template_smoke.yaml
```

如果你要对照 `referece_notebook/notebook.ipynb` 的标签和调参路径，再额外叠一层：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/default.yaml \
  --config configs/preset/notebook_compat.yaml \
  --data ./data_small.parquet \
  --output-dir ./artifacts/notebook-compat
```

这个 preset 依赖数据里已有 `pred_rel_return` 列。

## 4. 开始做自己的市场适配

建议顺序：

1. 修改 `configs/market/cn.yaml`
2. 只在现有 market profile 不够用时再扩展 `src/moneytree/markets/cn.py`
3. 再增加新特征与新模型配置
