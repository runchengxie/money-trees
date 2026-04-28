## 1. Shared Data Quality And Data Status

- [ ] 1.1 Add `src/moneytree/data_quality.py` with shared panel sanity mode validation, issue classification, and text/json rendering helpers.
- [ ] 1.2 Move TuShare-specific required columns, null-check columns, and local factor count checks behind reusable data quality functions without changing existing `--sanity-check off|warn|error` behavior.
- [ ] 1.3 Add `src/moneytree/data_status.py` with read-only collectors for base panel, raw TuShare cache manifest, factor-store manifest, and artifact directories.
- [ ] 1.4 Implement base panel status fields: file size, rows, columns, date range, date count, ticker count, duplicate `date,ticker` keys, required columns, null rates, price/volume/OHLC warnings, and errors.
- [ ] 1.5 Implement raw cache status by reading `manifest.sqlite` and aggregating source, API name, date range, shard count, row count, schema hash count, and content hash count.
- [ ] 1.6 Implement factor-store status by reading `manifest.json`, summarizing base panel metadata, family names, prefixes, paths, rows, columns, partitions, compression metadata, and missing file errors.
- [ ] 1.7 Implement artifact status for known Money Trees files such as `experiment_manifest.json`, metrics, run config, exported parquet files, and total directory size.
- [ ] 1.8 Add `src/moneytree/cli/data_status.py` with `--panel`, `--raw-cache`, `--factor-store`, `--artifacts`, `--format text|json`, and `--mode warn|error`.
- [ ] 1.9 Register `moneytree-data-status` and `moneytrees-data-status` in `pyproject.toml`.
- [ ] 1.10 Add tests for data-status CLI argument validation, text output, JSON output, warn mode, error mode, missing manifests, duplicate panel keys, and read-only behavior.
- [ ] 1.11 Update TuShare tests so current sanity wrapper behavior is covered through the shared data quality module.

## 2. External Alpha101/191 Factor Store

- [ ] 2.1 Refactor `factor_store.py` to expose a common partition writer for already-computed factor family frames.
- [ ] 2.2 Preserve the existing overlap-aware local Alpha158/360 generation path while routing its final parquet writes through the shared partition writer where practical.
- [ ] 2.3 Add external family validation in the factor-store write path for Alpha101 expected 101 columns and Alpha191 expected 191 columns.
- [ ] 2.4 Add an external factor-store writer that can add Alpha101/191 to an existing store when the base panel index matches.
- [ ] 2.5 Ensure the external writer preserves unrelated existing factor families and fails clearly on base panel misalignment.
- [ ] 2.6 Extend `moneytrees-dolphindb-alphas` with `--factor-store-output`, `--chunk-trade-dates`, and `--no-wide-output`.
- [ ] 2.7 Change DolphinDB alpha CLI output validation so at least one of `--output` or `--factor-store-output` is required.
- [ ] 2.8 Keep the existing wide-panel `--output` path and manifest behavior compatible with current tests.
- [ ] 2.9 Write external factor-store manifest metadata for requested families, generated families, field mapping, validation summary, DolphinDB version, client version, module versions, dtype, compression, and chunk size.
- [ ] 2.10 Confirm manifest sanitization excludes passwords, tokens, and secret-like values.
- [ ] 2.11 Add tests for factor-store-only output, wide-output compatibility, combined output, expected column counts, unknown output keys, all-null values, existing store append, and base panel mismatch.

## 3. Containerized Research Runtime

- [ ] 3.1 Add a root `Dockerfile` for a Python runner image using project-local source and selectable extras through a build argument.
- [ ] 3.2 Keep the runner image focused on Python, Money Trees CLIs, and optional Python dependencies; do not install DolphinDB server in the runner image.
- [ ] 3.3 Add `.dockerignore` entries for `.env`, `data/`, `artifacts/`, `cache/`, raw parquet outputs, SQLite manifests, generated artifacts, and other local runtime files.
- [ ] 3.4 Add `docker-compose.alpha.yml` with separate `moneytrees` and `dolphindb` services.
- [ ] 3.5 Configure compose volumes for `data/`, `artifacts/`, configs, and DolphinDB module/bootstrap paths without committing secrets.
- [ ] 3.6 Document expected environment variables and host-provided credentials without adding real tokens or passwords to tracked files.
- [ ] 3.7 Add lightweight validation where practical, such as checking that Docker files contain expected service names, mounts, and ignored paths.

## 4. Documentation

- [ ] 4.1 Add `docs/data_status.md` explaining raw TuShare cache, base panel, factor store, and artifacts as separate operational layers.
- [ ] 4.2 Document `moneytrees-data-status` examples for panel coverage, raw cache coverage, factor-store coverage, artifact status, JSON output, and `warn|error` modes.
- [ ] 4.3 Document storage and refresh guidance, including space estimation, refresh strategy, and cleanup guidance that requires dry-run in future cleanup tooling.
- [ ] 4.4 Update `docs/dolphindb_alpha101_191.md` with the new `--factor-store-output` workflow and the continued wide-panel compatibility path.
- [ ] 4.5 Update `docs/runbook.md` or cookbook examples with the recommended pipeline: TuShare base panel, local factor store, external Alpha101/191 factor-store write, backtest from manifest.
- [ ] 4.6 Update README with a concise link to `docs/data_status.md` and avoid moving detailed operational content into README.
- [ ] 4.7 Use the project Chinese terminology rules in user-facing Chinese docs, including `市场配置档`, `基准`, `可交易过滤`, `冒烟测试`, `预设配置`, `注册表`, and consistent `面板` or `panel` usage.

## 5. Parquet Storage Policy

- [ ] 5.1 Audit parquet-producing CLIs for missing `--row-group-size` support.
- [ ] 5.2 Extend relevant writers and CLIs so `compression`, `compression_level`, and `row_group_size` flow through `save_market_data()` or shared parquet helpers.
- [ ] 5.3 Preserve the current default `zstd` compression and default level 3.
- [ ] 5.4 Record row group size in manifests where compression options are already recorded.
- [ ] 5.5 Add tests for invalid compression-level combinations, invalid row group size, explicit row group propagation, and manifest metadata.
- [ ] 5.6 Confirm existing parquet files remain readable and no automatic migration or rewrite is introduced.

## 6. Verification And Rollout

- [ ] 6.1 Run focused tests for data status, TuShare data source sanity, factor store, DolphinDB alpha CLI, project identity scripts, and parquet helpers.
- [ ] 6.2 Run `uv run ruff check .`.
- [ ] 6.3 Run `uv run pytest -q` or document any optional dependency tests that cannot run in the current environment.
- [ ] 6.4 Verify `moneytrees-data-status --format json` output is stable enough for CI usage.
- [ ] 6.5 Verify `moneytrees-dolphindb-alphas` still reports a clear optional dependency error when DolphinDB Python client is not installed.
- [ ] 6.6 Verify no `.env`, tokens, runtime data, raw cache files, generated parquet files, or artifacts are added to version control.
