# Generate Alpha101/191 with DolphinDB

[简体中文](generate-alpha101-191-with-dolphindb.zh-CN.md)

This guide uses DolphinDB as an external producer for Alpha101/191. Money Trees consumes the offline-generated results; it does not call DolphinDB during backtests. The recommended output is a factor store. The older wide-parquet output remains available for compatibility.

## Current boundary

`docs/factor-catalog.csv` lists 810 factor columns:

| Family | Count | Project calculation path |
| --- | ---: | --- |
| Alpha101 | 101 | Generated locally by `build_alpha101_features` or externally by DolphinDB and then merged. |
| Alpha191 | 191 | Generated locally by `build_alpha191_features` or externally by DolphinDB and then merged. |
| Alpha158 | 158 | Generated locally by `build_alpha158_features`. |
| Alpha360 | 360 | Generated locally by `build_alpha360_features`. |

All 810 factors have a project calculation path. Alpha158/360 are generated locally in `qlib.py`. Alpha101/191 can be generated locally in pure Python by `classic.py` using cross-sectional semantics (see [classic-alphas-python.md](classic-alphas-python.md)), or through the external DolphinDB contract in this guide. DolphinDB and local implementations may differ in `rank`/`scale`, missing-value handling, and `SMA`/`DECAYLINEAR` semantics. Compare a small sample before formal use.

Recommended data flow:

```text
Versioned daily panel published by quant-market-data-platform
-> compute Alpha101/191 offline with DolphinDB
-> write alpha101 / alpha191 family partitions to data/factor_store/cn
-> backtest with moneytrees using the factor-store manifest
```

The compatibility wide-panel path remains available:

```text
Standard daily panel
-> compute Alpha101/191 offline with DolphinDB
-> write a wide parquet with alpha101_* / alpha191_* columns
-> backtest with moneytrees using that parquet
```

Features entering the model remain subject to `feature_lag_periods` in the market configuration. The default is `1`.

## Recommended WSL environment

For WSL development, the documented setup is:

```text
Windows Docker Desktop
-> WSL 2 backend
-> docker CLI inside the WSL distribution
-> single-node DolphinDB container
```

Keep project code in the WSL filesystem, for example `~/code/money-trees`, rather than under `/mnt/c/...`.

Check WSL from PowerShell:

```powershell
wsl --version
wsl -l -v
```

Ensure the development distribution uses WSL 2. In Docker Desktop, enable:

```text
Settings -> General -> Use WSL 2 based engine
Settings -> Resources -> WSL Integration -> Enable integration with your distro
```

Then check Docker from WSL:

```bash
docker version
docker ps
```

## DolphinDB container

The repository includes a Compose scaffold:

```bash
docker compose -f docker-compose.alpha.yml run --rm moneytrees \
  -lc 'moneytrees-dolphindb-alphas --help'
```

The Compose file defines separate `moneytrees` Python-runner and `dolphindb` server services. The runner mounts `data/`, `artifacts/`, and `docker/dolphindb/modules/`. The server mounts its own data directory so that the image's `/data/ddb/server/dolphindb` startup program is not overwritten. Pin the DolphinDB image tag, license, and module sources to versions verified in your environment.

Create local mount directories in the project root:

```bash
mkdir -p docker/dolphindb/modules docker/dolphindb/bootstrap
```

Start a single-node container. Replace the image tag with the version verified in your environment:

```bash
docker run -itd \
  --name dolphindb-alpha \
  --hostname host1 \
  -p 8848:8848 \
  -v "$PWD/docker/dolphindb/modules:/data/ddb/server/modules" \
  -v "$PWD/data/ddb/server/data:/data/ddb/server/data" \
  dolphindb/dolphindb:<ddb-version> \
  sh
```

Open the local web interface at:

```text
http://localhost:8848
```

The local development configuration commonly uses:

```text
admin / 123456
```

Treat this as a local-only development credential. Set a private password for any shared or exposed instance, and never expose the default credential to an untrusted network.

## DolphinDB modules

Place externally obtained or locally maintained modules in:

```text
docker/dolphindb/modules/
```

With this repository's `docker-compose.alpha.yml`, the directory is mounted read-only inside the DolphinDB server at:

```text
/data/ddb/server/data/modules
```

For the manual `docker run` example above, verify that the mount target matches the server modules directory used by your DolphinDB image.

Expected files:

```text
wq101alpha.dos
prepare101.dos
gtja191Alpha.dos
gtja191Prepare.dos
moneytreeAlpha.dos
```

These `.dos` files are prepared locally and are not committed with the repository. Obtain and configure them before running the guide. `wq101alpha.dos` and `gtja191Alpha.dos` provide formula modules; `prepare101.dos` and `gtja191Prepare.dos` provide preparation modules; `moneytreeAlpha.dos` is the Money Trees adapter wrapper. Before production use, verify module source, authorization, and versions, and record the module-version labels in the generation command.

`moneytreeAlpha.dos` should provide these functions:

```text
calcMoneyTreeAlpha101(rawData, startTime, endTime)
calcMoneyTreeAlpha191(rawData, startTime, endTime)
```

They return wide tables:

```text
tradetime, securityid, alpha101_001, ..., alpha101_101
tradetime, securityid, alpha191_001, ..., alpha191_191
```

The Python CLI uploads normalized input, invokes the wrapper, downloads and validates the result columns, and writes to the factor store or merges the factors into a compatibility wide panel.

After installing the modules and restarting DolphinDB, check module loading first:

```bash
uv run python -c 'import dolphindb as ddb; s=ddb.Session(); s.connect("127.0.0.1",8848,"admin","123456"); print(s.run("use wq101alpha; use prepare101; use gtja191Alpha; use gtja191Prepare; use moneytreeAlpha; 1"))'
```

Continue when this prints `1`. Before uploading the panel, the CLI also checks that required modules and wrapper functions exist and reports missing names directly. `--wq101-module-version`, `--gtja191-module-version`, and `--moneytree-alpha-module-version` record manifest metadata only; they do not change the DolphinDB `use` module names.

By default, the CLI reads its password from `DOLPHINDB_PASSWORD`. If that variable is unset or empty, the local development default is `123456`. An explicitly supplied `--password` must be non-empty. Do not use the development default on an exposed server.

## Field mapping

The CLI maps a Money Trees panel to DolphinDB input fields:

| DolphinDB field | Money Trees source |
| --- | --- |
| `tradetime` | `date` |
| `securityid` | `ticker` |
| `open` | Prefer `open_adj`, fall back to `open`. |
| `high` | Prefer `high_adj`, fall back to `high`. |
| `low` | Prefer `low_adj`, fall back to `low`. |
| `close` | Prefer `close_adj`, fall back to `close`. |
| `vwap` | Prefer `vwap_adj`, fall back to `vwap`. |
| `vol` | Prefer `volume`, fall back to `vol * 100`. |
| `cap` | Prefer `circ_mv`, fall back to `total_mv`; otherwise null. |
| `indclass` | `industry`; fill missing values with `UNKNOWN`. |
| `index_open` | `benchmark_open` |
| `index_close` | `benchmark_close` |

Alpha191 requires `benchmark_open` and `benchmark_close` in the input panel. Industry- and capitalization-related Alpha101 factors depend on `indclass` and `cap`. If the industry field is not point-in-time, historical backtests may contain look-ahead bias.

## Generate factors

The DolphinDB Python client is optional and is not a core dependency. Install the external-Alpha extra in the active environment:

```bash
uv sync --dev --extra external-alphas
```

For new research, start with a versioned panel published by `quant-market-data-platform`. The retained `moneytrees-tushare` command below is a deprecated compatibility path for reproducing older notebooks and workflows; see [data input migration](data-platform-migration.md).

```bash
uv run moneytrees-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily_alpha158_360.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --benchmark 000300.SH \
  --factor-family alpha158 \
  --factor-family alpha360
```

### Recommended factor-store output

When first connecting an environment, validate each family separately: run `--alpha101` to a temporary output, then `--alpha191` to a temporary output. After both checks pass, run both families into the target factor store. Alpha191 requires `benchmark_open` and `benchmark_close` in the input panel.

With parquet input and `--no-wide-output`, the CLI defaults to `--stream-input auto`. It divides target trading dates into `--chunk-trade-dates` windows, adds the historical context specified by `--dolphindb-warmup-trade-dates`, reads and uploads only that window, calls DolphinDB, downloads results for target dates only, and writes each partition immediately. This avoids constructing a multi-year, full-market input/output wide table in Python or the DolphinDB client. Pass `--overwrite` to regenerate an external factor family already recorded in the manifest. Compatibility wide-panel output still returns the complete wide table at once.

Streaming boundary: `--stream-input auto` applies only to parquet input with `--no-wide-output` and factor-store output. Wide-panel output, pickle input, or explicit `--stream-input off` uses the older full-input upload path. A multi-year, full-market panel can exhaust memory. The CLI runs a memory preflight before loading; bypass it with `--skip-memory-check` only when you intentionally accept the risk of an OOM kill.

Validate Alpha101 alone by retaining the connection and version options and changing the output directory:

```bash
uv run moneytrees-dolphindb-alphas \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn-alpha101-check \
  --no-wide-output \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --alpha101 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --stream-input auto \
  --overwrite \
  --dolphindb-warmup-trade-dates 260 \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

Validate Alpha191 separately with `--alpha191`:

```bash
uv run moneytrees-dolphindb-alphas \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn-alpha191-check \
  --no-wide-output \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --alpha191 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --stream-input auto \
  --overwrite \
  --dolphindb-warmup-trade-dates 260 \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

For the final factor store, separate runs by family are still recommended. Generate both with `--alpha101 --alpha191` only after each family has passed an individual check and the environment has sufficient memory:

```bash
uv run moneytrees-dolphindb-alphas \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn \
  --no-wide-output \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --alpha101 \
  --alpha191 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --stream-input auto \
  --overwrite \
  --dolphindb-warmup-trade-dates 260 \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

Backtest directly from the factor store:

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/factor_store/cn/manifest.json \
  --output-dir artifacts/xgb-alpha-all
```

### Compatibility wide-panel output

The older path can still generate and merge Alpha101/191 into a wide panel:

```bash
uv run moneytrees-dolphindb-alphas \
  --input data/cn_daily_alpha158_360.parquet \
  --output data/cn_daily_alpha_all.parquet \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --alpha101 \
  --alpha191 \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

`scripts/build_dolphindb_alphas.py` remains as a compatibility wrapper. The current entry point is `moneytrees-dolphindb-alphas`.

Legacy output files:

```text
data/cn_daily_alpha_all.parquet
data/cn_daily_alpha_all.parquet.factor_manifest.json
```

Then run a backtest as usual:

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha_all.parquet \
  --output-dir artifacts/xgb-alpha-all
```

## Metadata manifest

Each successful generation writes a manifest containing:

- Factor source and family.
- Input/output file hashes and schema summaries.
- DolphinDB host, port, user, server version, and Python-client version.
- WQ101, GTJA191, and `moneytreeAlpha` module-version labels.
- Selected price, volume, market-cap, industry, and benchmark fields.
- Fallback fields and missing optional fields.
- Column-completeness and key-matching validation results.

The manifest does not record passwords, tokens, `.env` contents, or TuShare tokens.

## Validation rules

The generator rejects:

- Duplicate `date, ticker` keys in the input panel.
- Missing any requested column in `alpha101_001`…`alpha101_101` or `alpha191_001`…`alpha191_191`.
- Output containing `alpha101_` or `alpha191_` columns outside the requested families.
- DolphinDB output containing `date, ticker` keys absent from the input panel.
- No matching input/output keys, or all-null requested factor values for the matching keys.

These checks enforce the external factor-production data contract.

## Research risks

- Operators such as `rank`, `ts_rank`, `decay_linear`, and `SMA` may differ across implementations.
- `vwap`, adjusted prices, market capitalization, and industry classification can materially change factor values.
- Industry-related Alpha101 factors require point-in-time industry classifications.
- Alpha191 benchmark open/close fields must match the backtest benchmark.
- Do not compare mixed Alpha101/191 implementations without first pinning DolphinDB and module versions.
