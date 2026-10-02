# Factor mining

[简体中文](https://runchengxie.github.io/money-trees/zh-CN/factor-mining/)

This guide covers genetic-programming (GP) search for new composite factors built from existing Alpha factors. The feature was ported from `factor_generator.py` in the `wu-alpha191-alpha101` reference repository, adapted to the standard Money Trees `date, ticker` panel, and uses cross-sectional Spearman IC as its fitness signal.

## Method

- Terminals: Alpha columns in the panel, such as `alpha101_*`, `alpha191_*`, `alpha158_*`, and `alpha360_*`, plus constant window parameters `{3, 5, 10, 20, 60}`.
- Operators: `+ - * / neg log sqrt cs_rank` and `ts_delay ts_corr ts_mean ts_std ts_min ts_max ts_delta`.
- Fitness: absolute Spearman IC between a composite factor and future N-day returns, minus a complexity penalty.
- Validation: after evolving the best expression in the training window, calculate IC, ICIR, and average quintile returns in a held-out window.

## CLI

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

`--data` accepts a standard panel in parquet or pickle format, or a factor-store `manifest.json`.

## Common options

| Option | Description |
| --- | --- |
| `--factor-prefixes` | Repeatable factor-column prefixes used as terminals. |
| `--factor-column` | Repeatable explicit factor-column names. If omitted, all recognized Alpha factor columns in the panel are used. |
| `--start-date` / `--end-date` | Training window. |
| `--test-start-date` / `--test-end-date` | Held-out validation window. |
| `--future-return-period` | Future-return horizon in trading days; defaults to 5. |
| `--pop-size` / `--max-gen` / `--max-depth` | Population size, maximum generations, and maximum expression-tree depth. |
| `--seed` | Random seed for reproducibility. |
| `--neutralize` | Neutralize market capitalization during validation before calculating quintile returns. |
| `--output-dir` | Output directory for `mining_report.json` and `best_factor.txt`. |

## Output and limitations

`mining_report.json` contains:

- `train.best_expression`: best expression string.
- `train.best_fitness`: training fitness.
- `test`: held-out mean IC, IC standard deviation, ICIR, and average quintile returns.
- `generations`: best and mean fitness by generation.

Mined expressions are candidate factors only. Evaluate stability, factor correlation, and neutralized performance in the full research workflow before using them.
