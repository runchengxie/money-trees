# Maintenance Backlog

本文记录当前暂不强行重构、但后续值得拆分和治理的模块边界。它不是主运行手册；实施前仍应创建或更新对应 OpenSpec change。

## 大文件和职责边界

| 文件 | 当前问题 | 后续建议 |
| --- | --- | --- |
| `src/moneytree/runner.py` | 回测 orchestration、holdout、输出写入、summary 组装集中在一个文件。 | 拆出 orchestration、outputs、holdout、run config summary。 |
| `src/moneytree/backtest.py` | 滚动窗口、指标、诊断和序列拼接混在一起。 | 拆出 metrics、rolling、diagnostics。 |
| `src/moneytree/portfolio.py` | 启发式权重、QP、协方差估计和约束逻辑集中。 | 拆成 portfolio config、heuristic、QP、risk/covariance helpers。 |
| `src/moneytree/model.py` | 随机森林工具、评分、调参、特征选择和 legacy notebook 路径混在一起。 | 拆出 scoring、model selection、random forest tuning、legacy compatibility。 |
| `src/moneytree/data_sources/tushare.py` | TuShare client、cache、标准化和 manifest 迁移集中。 | 拆出 client、cache、standardize、manifest migration。 |
| `src/moneytree/factors/external.py` | 外部 Alpha 字段映射、校验、merge 和 manifest 逻辑集中。 | 后续可拆出 field mapping、validation、manifest helpers。 |

## 历史和兼容工具

- `scripts/convert_pickle_to_parquet.py` 是旧 pickle 数据迁移工具，不属于主研究链路。
- `scripts/build_dolphindb_alphas.py` 是兼容 wrapper；正式入口是 `moneytrees-dolphindb-alphas`。
- `configs/preset/notebook_compat.yaml` 是过渡兼容路径；正式文档使用 `configs/preset/legacy_notebook_compat.yaml`。

## 质量门槛

日常开发至少运行：

```bash
uv run ruff check .
uv run pytest -q
```

涉及 TuShare、DolphinDB、模型适配器、配置解析、输出文件或数据契约时，应补充对应专项测试。
