## Context

Money Trees currently treats `date, ticker` as the canonical panel shape and supports three storage-producing paths: TuShare raw parquet cache, standard panel parquet, and experiment artifacts. Local Alpha158/360 generation appends 518 columns to the panel, while external Alpha101/191 generation appends another 292 columns after DolphinDB validation. The simple wide-panel route is useful for smoke tests and notebooks, but it duplicates base fields and factor families across `cn_daily_alpha158_360.parquet`, `cn_daily_alpha_all.parquet`, `export_parquet`, and experiment copies.

The current implementation also loads parquet inputs with `pd.read_parquet(path)` and computes factor columns through pandas arithmetic that defaults to `float64`. For a five-year, full-market, 810-factor panel, factor values alone are roughly 39 GB as raw `float64` values before compression and duplicated outputs. The first implementation step should reduce this footprint without changing formulas, optional dependency behavior, or the existing wide-panel workflow.

## Goals / Non-Goals

**Goals:**

- Reduce default storage for alpha factor columns by supporting `float32` persistence, with a documented `float64` escape hatch.
- Keep `date, ticker` as the canonical key for both wide panels and split factor-family files.
- Add factor-family or factor-prefix selection so backtests and diagnostics can avoid loading unused Alpha101/191/158/360 columns.
- Make parquet column pruning part of the backtest data path when selected columns can be resolved from the parquet schema.
- Document expected storage scale, recommended paths, and artifact retention rules.
- Define an additive medium-term factor-store layout that separates base panel data from factor families and records the combined dataset through a manifest.

**Non-Goals:**

- Do not introduce DuckDB, Polars, Delta Lake, LakeFS, or other storage engines as required dependencies.
- Do not remove or break existing single-file wide-panel parquet workflows.
- Do not change Alpha101/191/158/360 formulas, column names, or the external-alpha manifest validation contract.
- Do not automatically delete raw cache, factors, panels, or artifacts.
- Do not make DolphinDB, TuShare, XGBoost, or Optuna core dependencies.

## Decisions

1. Use a shared factor-column classifier and dtype coercion helper.

   Factor columns are the existing `alpha101_`, `alpha191_`, `alpha158_`, and `alpha360_` prefixes. A helper in the data or factors layer should identify these columns and cast only those columns when requested. The default persisted dtype for generated alpha columns should be `float32`, with a CLI/config option to keep `float64`.

   Alternatives considered: globally downcast every numeric column, or leave factor dtypes unchanged. Global downcasting risks changing market data, labels, benchmark fields, and identifiers; leaving dtypes unchanged misses the highest-return storage reduction.

2. Preserve wide-panel compatibility as the short-term path.

   The TuShare and DolphinDB CLIs should continue writing one parquet file by default. New options should change dtype and selected families without requiring users to adopt a new layout. Existing docs and tests that expect a wide panel should remain valid.

   Alternatives considered: immediately replace wide panels with a mandatory factor store. That would reduce duplication faster, but it would create a larger migration and make notebooks, smoke tests, and external-alpha workflows harder to reason about.

3. Add explicit factor selection before introducing a separate store.

   Backtest settings should support factor include/exclude prefixes or families. For parquet inputs, the loader can inspect the parquet schema with the existing `pyarrow` dependency, build the required column list, and call `pd.read_parquet(..., columns=...)`. For pickle inputs or unsupported formats, it can fall back to loading the file and filtering in memory.

   Alternatives considered: rely only on model feature selection after loading. That still pays the full IO and memory cost for unused factor families.

4. Treat factor store as additive medium-term infrastructure.

   The medium-term layout should have durable base panel files and separate family files such as `data/factors/alpha158.parquet`, each keyed by `date, ticker`. A manifest should describe the base path, factor family paths, row counts, column counts, dtype policy, and generation metadata. Loading from the manifest should join only requested families.

   Alternatives considered: one parquet dataset partitioned by date for all columns. That helps date-window scans but still couples all factor families and encourages repeated rewrites when one family changes.

5. Keep cleanup destructive actions out of this change.

   The first storage tooling should be inspection-only or dry-run by default. Any future garbage collection command must report what it would remove and require an explicit non-dry-run option.

   Alternatives considered: automatic cache or artifact deletion. That is risky for research reproducibility and conflicts with project data-safety rules.

## Risks / Trade-offs

- `float32` can create small numerical differences in factor diagnostics and model inputs. Mitigation: make `float64` selectable and document the trade-off.
- Prefix selection can accidentally exclude needed model features if configuration is too broad. Mitigation: report selected prefixes, final feature counts, and missing requested prefixes in run summaries.
- Parquet schema inspection is parquet-specific. Mitigation: keep pickle behavior compatible by falling back to full-file load.
- Joining split factor files can introduce row alignment bugs. Mitigation: require `date, ticker` uniqueness, validate row counts, and test missing/extra key behavior before enabling manifest loading.
- Factor-store implementation is larger than dtype and documentation work. Mitigation: implement in phases, with the wide-panel path kept as the stable default until manifest loading is covered by tests.

## Migration Plan

1. Short term: add dtype helpers, CLI/config options, tests, and documentation while keeping wide-panel outputs as the default.
2. Short term: add factor prefix/family selection and parquet column pruning for backtests.
3. Medium term: add factor-store write path and manifest schema as an additive option.
4. Medium term: add factor-store/manifest read path for backtests and diagnostics.
5. Follow-up: add `data inspect` and dry-run garbage-collection commands after the storage layout and manifests are stable.

Rollback is straightforward for the short-term changes: set factor dtype to `float64` and run existing wide-panel commands. Factor-store adoption should remain opt-in until the manifest loader is validated.

## Open Questions

- Should the CLI option be named `--factor-dtype` across both TuShare and DolphinDB alpha commands, or should external alpha generation use a separate `--alpha-dtype` alias for clarity?
- Should prefix selection live under `market` config, `data` config, or a new top-level `features` section?
- Should factor-store paths be generated directly by existing CLIs or by a later dedicated `moneytrees-factors` command?
