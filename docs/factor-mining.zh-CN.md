# 因子挖掘

[English page](factor-mining.md)

本文说明如何用遗传算法（GP）在已有 Alpha 因子上挖掘新的合成因子。该功能移植自 `wu-alpha191-alpha101` 参考仓库的 `factor_generator.py`，适配 Money Trees 的标准 `date, ticker` 面板，并以横截面 Spearman IC 作为适应度。

## 思路

- 终端（terminals）：面板中的 Alpha 因子列（`alpha101_*`、`alpha191_*`、`alpha158_*`、`alpha360_*` 等），以及常量窗口参数 `{3, 5, 10, 20, 60}`。
- 算子：`+ - * / neg log sqrt cs_rank` 和 `ts_delay ts_corr ts_mean ts_std ts_min ts_max ts_delta`。
- 适应度：合成因子值对未来 N 日收益的 Spearman IC 绝对值，减去复杂度惩罚。
- 验证：在训练窗口进化出最优表达式后，在留出窗口计算 IC、ICIR 和五分位数组平均收益。

## CLI 用法

```bash
uv run moneytrees-factor-mining \
  --data data/factor_store/cn_daily/manifest.json \
  --factor-prefixes alpha101 \
  --factor-prefixes alpha191 \
  --start-date 2018-01-01 \
  --end-date 2023-12-31 \
  --test-start-date 2024-01-01 \
  --test-end-date 2024-12-31 \
  --future-return-period 5 \
  --pop-size 100 \
  --max-gen 20 \
  --max-depth 4 \
  --seed 42 \
  --output-dir artifacts/mining
```

`--data` 支持标准面板 parquet/pickle，或因子仓库的 `manifest.json`。

## 常用参数

| 参数 | 说明 |
| --- | --- |
| `--factor-prefixes` | 可重复传入的因子列前缀，作为终端集合。 |
| `--factor-column` | 可重复传入的显式因子列名。缺省时使用面板中全部已知 Alpha 因子列。 |
| `--start-date` / `--end-date` | 训练窗口。 |
| `--test-start-date` / `--test-end-date` | 留出验证窗口。 |
| `--future-return-period` | 未来收益周期（交易日），默认 5。 |
| `--pop-size` / `--max-gen` / `--max-depth` | 种群大小、最大代数、表达式树最大深度。 |
| `--seed` | 随机种子，保证可复现。 |
| `--neutralize` | 验证时对市值做中性化后再计算分位收益。 |
| `--output-dir` | 输出目录，写入 `mining_report.json` 和 `best_factor.txt`。 |

## 输出

`mining_report.json` 包含：

- `train.best_expression`：最优表达式字符串。
- `train.best_fitness`：训练适应度。
- `test`：留出窗口的平均 IC、IC 标准差、ICIR 和五分位数组平均收益。
- `generations`：逐代最优/平均适应度。

注意：挖掘结果只是候选因子，仍需在完整研究链路里评估稳定性、因子相关性和中性化后再投入使用。
