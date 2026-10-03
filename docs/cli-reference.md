# CLI reference

[Chinese version](https://runchengxie.github.io/money-trees/zh-CN/cli-reference/)

Examples use the `moneytrees*` commands. The `moneytree*` aliases remain for compatibility. Data production is no longer the long-term path of this repository; use `quant-market-data-platform` for new data and keep `moneytrees-tushare` for migration and historical reproduction.

## Commands and aliases

| Recommended command | Compatibility alias | Purpose |
| --- | --- | --- |
| `moneytrees` | `moneytree` | Run a configured backtest. |
| `moneytrees-tushare` | `moneytree-tushare` | Build a standard `date, ticker` panel from TuShare. |
| `moneytrees-factor-store` | `moneytree-factor-store` | Build a local Alpha158/360 factor store. |
| `moneytrees-dolphindb-alphas` | `moneytree-dolphindb-alphas` | Generate external Alpha101/191 factors through DolphinDB. |
| `moneytrees-alpha101-191-python` | `moneytree-alpha101-191-python` | Generate Alpha101/191 locally in Python. |
| `moneytrees-factor-mining` | `moneytree-factor-mining` | Mine factors with the genetic-programming workflow. |
| `moneytrees-data-status` | `moneytree-data-status` | Read-only status check for caches, panels, stores, and artifacts. |
| `moneytrees-data-snapshot` | `moneytree-data-snapshot` | Write lightweight metadata snapshots. |
| `moneytrees-data-release` | `moneytree-data-release` | Build GitHub Release-friendly data assets. |
| `moneytrees-parquet-rewrite` | `moneytree-parquet-rewrite` | Rewrite parquet or migrate trusted pickle. |
| `moneytrees-factor-evidence` | `moneytree-factor-evidence` | Produce an aggregate-only public Alpha evidence snapshot. |

## `moneytrees`

| Option | Meaning |
| --- | --- |
| `--config` | Repeatable configuration files; later files override earlier ones. |
| `--data` | Override the configured panel or factor-store `manifest.json`. |
| `--output-dir` | Override the backtest artifact directory. |
| `--set` | Repeatable `dotted.path=value` configuration override. |

## `moneytrees-tushare` (deprecated compatibility command)

Use published panels from `quant-market-data-platform` for new research. Keep this command for old notebook migration and historical reproduction.

| Option | Meaning |
| --- | --- |
| `--start-date`, `--end-date` | Date range, in `YYYYMMDD` or `YYYY-MM-DD` format. |
| `--output` | Output path for the canonical panel parquet. |
| `--benchmark` | Benchmark code; defaults to `000300.SH`. |
| `--tickers` | Comma-separated symbols; empty selects all daily symbols returned by TuShare. |
| `--factor-family` | Repeatable `alpha158` or `alpha360` local factor family. |
| `--cache-dir` | Raw cache directory, partitioned by endpoint and trading date. |
| `--cache-compression`, `--cache-compression-level`, `--cache-row-group-size` | Raw cache parquet writing options. |
| `--refresh-cache` | Ignore and rewrite existing raw cache entries. |
| `--refresh-recent-days` | Refresh the latest N trading days in cache mode. |
| `--proxy-mode`, `--proxy-url`, `--no-fallback-direct` | Proxy controls. `direct` ignores shell proxy variables, `env` uses them, and `proxy` uses `--proxy-url`. |
| `--request-interval-seconds` | Minimum wait between real TuShare requests; cache hits do not wait. |
| `--rate-limit-retries`, `--rate-limit-wait-seconds` | Retry count and wait for rate-limit errors. |
| `--sanity-check` | Normalized-data check: `off`, `warn`, or `error`. |
| `--complete-calendar` | Fill the trading-date × symbol grid and mark missing-price rows as suspended. |
| `--raw-features`, `--factor-dtype` | Use unadjusted fields for local Alpha158/360 and choose the factor column dtype. |
| `--skip-daily-basic`, `--skip-adj-factor`, `--skip-limits`, `--skip-suspend`, `--skip-stock-basic` | Skip named TuShare endpoints. |
| `--compression`, `--compression-level`, `--row-group-size` | Output panel parquet writing options. |
| `--progress`, `--progress-every` | Report download and factor-generation progress. |

## `moneytrees-factor-store`

| Option | Meaning |
| --- | --- |
| `--input` | Base panel parquet or trusted pickle. |
| `--output-dir` | Factor-store directory. |
| `--factor-family` | Repeatable `alpha158` or `alpha360`. |
| `--raw-features` | Use unadjusted OHLCV/VWAP fields for local factors. |
| `--factor-dtype` | `float32` or `float64` factor columns. |
| `--chunk-trade-dates` | Target trading dates per partition. |
| `--compression`, `--compression-level`, `--row-group-size` | Partition parquet writing options. |
| `--overwrite` | Recompute an existing factor family. |
| `--progress` | Report partition progress. |

## `moneytrees-dolphindb-alphas`

| Option | Meaning |
| --- | --- |
| `--input` | Canonical panel parquet or trusted pickle. |
| `--output` | Compatible wide-panel output path. |
| `--manifest-output` | Wide-panel metadata path; defaults to `<output>.factor_manifest.json`. |
| `--factor-store-output` | Alpha101/191 factor-store output directory. |
| `--no-wide-output` | Write only the factor store. |
| `--host`, `--port`, `--user`, `--password` | DolphinDB connection. Password defaults to `DOLPHINDB_PASSWORD`, then the local default. |
| `--family`, `--alpha101`, `--alpha191` | Select external factor families. |
| `--alpha101-function`, `--alpha191-function` | DolphinDB wrapper function names. |
| `--wq101-module-version`, `--gtja191-module-version`, `--moneytree-alpha-module-version` | Metadata version labels; they do not change DolphinDB `use` module names. |
| `--raw-price-fields` | Use unadjusted prices when adjusted and unadjusted inputs coexist. |
| `--factor-dtype` | `float32` or `float64` factor columns. |
| `--compression`, `--compression-level`, `--row-group-size` | Output parquet writing options. |
| `--chunk-trade-dates` | Trading dates per factor-store partition and per streamed computation window. |
| `--overwrite` | Recompute an existing factor family. |
| `--dolphindb-warmup-trade-dates` | Extra history per streamed computation window. |
| `--stream-input` | For parquet plus `--no-wide-output`, `auto` uploads one window at a time; `off` uses the legacy full-input upload. |
| `--skip-memory-check` | Skip input memory preflight only when accepting out-of-memory risk. |
| `--progress` | Report partition writes. |

## `moneytrees-alpha101-191-python`

| Option | Meaning |
| --- | --- |
| `--input` | Canonical panel parquet or trusted pickle. |
| `--output` | Compatible wide-panel output path. |
| `--manifest-output` | Wide-panel metadata path; defaults to `<output>.factor_manifest.json`. |
| `--factor-store-output` | Alpha101/191 factor-store output directory. |
| `--no-wide-output` | Write only the factor store. |
| `--family`, `--alpha101`, `--alpha191` | Select locally generated factor families. |
| `--raw-price-fields` | Use unadjusted prices; adjusted prices are preferred by default. |
| `--factor-dtype` | `float32` or `float64` factor columns. |
| `--compression`, `--compression-level`, `--row-group-size` | Output parquet writing options. |
| `--chunk-trade-dates` | Trading dates per factor-store partition. |
| `--overwrite` | Recompute an existing factor family. |
| `--progress` | Report per-factor and partition progress. |

The [Python Alpha101/191 guide](classic-alphas-python.md) explains calculation semantics.

## `moneytrees-factor-mining`

| Option | Meaning |
| --- | --- |
| `--data` | Canonical panel parquet/pickle or factor-store `manifest.json`. |
| `--factor-prefixes`, `--factor-column` | Repeatable factor-column prefixes or explicit factor columns for GP terminals. |
| `--start-date`, `--end-date` | Training window. |
| `--test-start-date`, `--test-end-date` | Holdout window. |
| `--future-return-period` | Future-return horizon in trading days; defaults to 5. |
| `--pop-size`, `--max-gen`, `--max-depth` | Population, generation, and tree-depth limits. |
| `--seed` | Random seed. |
| `--complexity-penalty`, `--crossover-rate`, `--mutation-rate`, `--elitism-rate`, `--tournament-size` | GP hyperparameters. |
| `--neutralize` | Neutralize market value before holdout quantile-return evaluation. |
| `--output-dir` | Required; writes `mining_report.json` and `best_factor.txt`. |

See the [factor-mining guide](factor-mining.md) for examples.

## `moneytrees-data-status`

| Option | Meaning |
| --- | --- |
| `--panel` | Base `date, ticker` panel parquet or trusted pickle. |
| `--raw-cache` | TuShare raw cache directory or `manifest.sqlite`. |
| `--factor-store` | Factor-store directory or `manifest.json`. |
| `--artifacts` | Backtest artifact directory. |
| `--factor-family`, `--factor-families` | Limit checks to selected families, repeatable or comma-separated. |
| `--skip-factor-quality` | Check manifests and files without scanning factor values. |
| `--allow-factor-column` | Permit a known all-null, high-null, or constant column. |
| `--progress` | Report quality scan progress. |
| `--format` | `text` or `json`. |
| `--mode` | Data-issue exit policy: `warn` or `error`. |

This command is read-only. It does not refresh caches, repair panels, rewrite stores, or change artifacts.

## `moneytrees-data-snapshot`

| Option | Meaning |
| --- | --- |
| `--panel`, `--output-dir` | Required base panel and metadata snapshot directory. |
| `--raw-cache` | Optional raw cache directory or `manifest.sqlite`. |
| `--factor-store` | Optional factor-store directory or `manifest.json`. |
| `--label` | Optional human-readable snapshot label. |
| `--note` | Repeatable note written to `dataset_meta.json` and the snapshot README. |
| `--format` | `text` or `json`. |

Snapshots record metadata and checksums and refer to, rather than copy, large data files.

## `moneytrees-data-release`

| Option | Meaning |
| --- | --- |
| `--output-dir` | Required asset directory; accepts `/mnt/d/...` and `D:/...` paths. |
| `--panel`, `--raw-cache`, `--factor-store` | Optional panel, cache, and factor-store inputs. |
| `--max-asset-size-mb` | Size limit per generated asset; defaults to 1536 MiB. |
| `--label` | Optional human-readable release label. |
| `--note` | Repeatable note in `manifest.json` and README. |
| `--dry-run` | Preview assets without writing or uploading. |
| `--overwrite` | Replace generated files of the same name in `--output-dir`. |
| `--no-resume` | Disable reuse of resumable output; existing files require `--overwrite`. |
| `--progress` | Report asset generation progress to stderr. |
| `--skip-space-check` | Skip available-space preflight on the target filesystem. |
| `--github-repo`, `--github-tag` | `OWNER/REPO` and release tag for GitHub upload. |
| `--upload`, `--create-release` | Upload with GitHub CLI; optionally create the release first. |
| `--release-title`, `--clobber` | Title when creating a release and GitHub CLI overwrite option when uploading. |
| `--format` | `text` or `json`. |

Directory inputs become uncompressed tar partitions. A file over the limit is split into `.partNNNofMMM` parts. By default this command only generates local assets; GitHub access requires explicit `--upload`.

## `moneytrees-parquet-rewrite`

| Option | Meaning |
| --- | --- |
| `--input` | Parquet or trusted pickle input. |
| `--output` | Parquet output. |
| `--compression`, `--compression-level`, `--row-group-size` | Output parquet writing options. |
| `--overwrite` | Replace an existing output; in-place rewrites remain forbidden. |
| `--no-verify` | Skip post-write row, column, and index checks. |

Only load trusted historical pickle files. Prefer parquet for current research. Optional integrations such as XGBoost, TuShare, DolphinDB, and Optuna must report missing extras clearly.

## `moneytrees-factor-evidence`

This command produces aggregate-only research evidence, not a full strategy backtest. See the [public factor-evidence guide](public-factor-evidence.md) for interpretation and publication limits.

| Option | Meaning |
| --- | --- |
| `--panel`, `--factor-store`, `--factor-store-archive` | Exactly one required source: a panel, partitioned store manifest, or uncompressed store archive. |
| `--families` | Comma-separated store families; defaults to all. |
| `--date-start`, `--date-end` | Inclusive store date filters. |
| `--factors` | Required comma-separated names or one-name-per-line text file; store sources require `all` or `*`. |
| `--return-column` | Forward-return column; defaults to `next_period_return`. |
| `--benchmark-return-column`, `--benchmark-name` | Optional realized daily benchmark return column and readable label for regime slices. |
| `--regime-window` | Prior trading days used for regime labels; defaults to 252. |
| `--holding-period-days` | Forward holding period; required before inferential diagnostics are emitted. |
| `--data-version`, `--code-revision` | Input version and source revision recorded in the snapshot. |
| `--output` | Required aggregate snapshot JSON path. |
| `--quality-output` | Optional aggregate-only signal-quality JSON path. |
| `--evidence-v1-output` | Optional unified `factor_evidence.v1` JSON path. |
| `--group-count` | Return-group count; defaults to 5. |
| `--format` | CLI output as `text` or `json`. |
