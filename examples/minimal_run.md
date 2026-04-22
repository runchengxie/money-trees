# Minimal Run

这个模板的最小工作流只做两件事：先确认脚手架能跑，再开始替换市场实现。

## 1. 安装依赖

```bash
uv sync --dev
```

## 2. 准备一个最小数据文件

数据至少需要满足当前 `us` profile 的列契约：

- `date`
- `ticker`
- `next_period_return`
- `spy_cum_ret`
- `spy_next_period_return`

如果你已经在做 A 股衍生仓库，先实现并注册自己的 `cn` market profile，再改用 `configs/market/cn.yaml`。

## 3. 运行 smoke 配置

```bash
make smoke DATA=./data_small.parquet OUTPUT=./artifacts/template-smoke
```

等价的直接命令：

```bash
uv run treealpha-backtest \
  --config configs/market/us.yaml \
  --config configs/model/rf.yaml \
  --config configs/backtest/smoke.yaml \
  --data ./data_small.parquet \
  --output-dir ./artifacts/template-smoke
```

## 4. 开始做自己的市场适配

建议顺序：

1. 修改 `configs/market/*.yaml`
2. 替换 `src/treealpha/markets/*.py`
3. 再增加新特征与新模型配置
