## Context

Money Trees currently has the main building blocks for the research pipeline:

- `moneytrees-tushare` can build the canonical `date, ticker` panel and writes raw cache metadata to `manifest.sqlite`.
- `build_market_data_sanity_report()` already summarizes panel quality, but TuShare wraps it through a private `_emit_tushare_sanity_report()` helper.
- `moneytrees-factor-store` generates local Alpha158/360 factor families into a factor store with partitioned family files.
- `moneytrees-dolphindb-alphas` generates external Alpha101/191 factors through DolphinDB and validates the external column contract, but its main output is still a merged wide panel.
- The backtest runner can already load a factor-store manifest directly.
- Parquet defaults already use `zstd` level 3 through `DEFAULT_PARQUET_COMPRESSION`; the remaining work is consistent CLI exposure and documentation.
- The repository does not currently include Docker or compose runtime definitions.

The change should strengthen operational behavior without changing the core research contract: `date, ticker` remains the canonical panel key, DolphinDB remains optional and external to core dependencies, runtime data stays outside version control, and existing wide-panel workflows continue to work.

## Goals / Non-Goals

**Goals:**

- Provide one read-only status command for base panel, raw TuShare cache, factor store, and artifacts.
- Reuse the same data quality rules from TuShare download checks and the independent status command.
- Let DolphinDB Alpha101/191 outputs write directly to the Money Trees factor store with validation and manifest metadata.
- Keep the existing `moneytrees-dolphindb-alphas --output` wide panel path compatible.
- Add a Python runner Dockerfile and compose setup where DolphinDB is a separate service.
- Document the four operational data layers and parquet storage defaults.
- Standardize parquet writer options exposed by CLIs.

**Non-Goals:**

- Do not rewrite Alpha101/191 formulas in Python.
- Do not move DolphinDB into core dependencies.
- Do not make the Python image contain DolphinDB server runtime.
- Do not perform destructive cleanup, cache deletion, or automatic repair from `moneytrees-data-status`.
- Do not require a migration of existing raw cache or existing wide parquet files.
- Do not implement DolphinDB-side chunked Alpha101/191 computation in the first version.

## Decisions

### Decision: Split quality rules from status collection

Create `moneytree.data_quality` for shared panel sanity rules, mode handling, and rendering helpers. Create `moneytree.data_status` for filesystem and manifest inspection. Keep `moneytree.cli.data_status` as the argparse entry point.

Rationale: TuShare download sanity checks and data-status need identical pass/fail behavior. Separating quality rules from IO-oriented status collection keeps the reusable validation code small and prevents the TuShare data source from becoming the owner of general data quality policy.

Alternative considered: keep `_emit_tushare_sanity_report()` private and duplicate status behavior in the new CLI. That would make future rule changes drift across two call sites.

### Decision: Make data-status read-only and mode-driven

`moneytrees-data-status` reads inputs and reports status. It does not fix, delete, rewrite, compact, or refresh anything. `--mode warn` reports issues and exits successfully unless argument parsing fails. `--mode error` exits non-zero when any checked layer has errors. `--format text|json` controls output only.

Rationale: Data inspection must be safe to run before expensive research jobs or in CI. Cleanup and repair workflows need separate explicit commands with dry-run behavior.

Alternative considered: include `--fix` or cleanup actions in the first version. That expands the blast radius before the read-only contract is proven.

### Decision: Inspect manifests first and scan large data only when needed

Base panel status loads the provided panel because row count, date coverage, duplicate keys, and null rates require actual data. Raw TuShare cache status reads `manifest.sqlite` and summarizes by API, date range, row counts, shards, schema hashes, and content hashes. Factor store status reads `manifest.json` and verifies family metadata; alignment checks can load factor files when needed, but the normal summary should prefer manifest metadata where possible.

Rationale: The command must remain practical on large A-share datasets. Full raw-cache scans would be slow and surprising.

Alternative considered: always read every parquet file. That gives deeper validation but turns status into a heavy data audit command.

### Decision: Write external Alpha101/191 to factor store after full DolphinDB calculation

The first external factor-store path should upload the complete input panel to DolphinDB, calculate each requested family over the full available date range, validate the returned family against the `date, ticker` key and expected column set, then write the resulting family frame into factor-store partitions on the Python side.

Rationale: Alpha101/191 include rolling, delay, rank, and correlation style operators. Naive DolphinDB-side chunking can silently corrupt partition boundaries without overlap logic. Full calculation with partitioned storage gives safer semantics first.

Alternative considered: compute Alpha101/191 in DolphinDB date chunks immediately. That should wait until overlap windows and boundary tests are specified.

### Decision: Add a common partition writer for factor families

Refactor `factor_store.py` so local and external family writers share a partition writer that accepts an already-computed factor frame. Local Alpha158/360 still use their existing overlap-aware generation path. External Alpha101/191 use the common writer after DolphinDB validation.

Rationale: The store layout and manifest shape should be consistent across local and external families. Shared writing code reduces drift in path, partition, dtype, compression, and manifest metadata behavior.

Alternative considered: have DolphinDB CLI write custom files beside the factor store. That creates a second storage convention and weakens the backtest runner's factor-store contract.

### Decision: Preserve wide output compatibility

`moneytrees-dolphindb-alphas` should support both the current `--output` wide panel path and a new `--factor-store-output` path. At least one output path is required. A `--no-wide-output` option can be added only when `--factor-store-output` is present.

Rationale: Existing workflows and tests rely on the wide panel output. The factor-store path should be additive and adoptable in stages.

Alternative considered: replace `--output` with factor store. That is an unnecessary breaking change.

### Decision: Keep Docker runtime layered

Add a main Python `Dockerfile` that installs Money Trees with selectable extras through a build argument. Add `docker-compose.alpha.yml` with a `moneytrees` service and a separate `dolphindb` service. Use volumes for `data/`, `artifacts/`, configs, and any DolphinDB modules. Do not bake `.env`, tokens, raw data, cache, or generated artifacts into images.

Rationale: The Python environment and DolphinDB server have different dependency and licensing boundaries. Compose should express that boundary instead of hiding it inside one image.

Alternative considered: install DolphinDB server in the Python image. That would blur optional dependency boundaries and make the runtime harder to audit.

### Decision: Treat compression as policy convergence

Keep the existing default of `zstd` level 3. Add missing `--row-group-size` exposure where parquet-producing CLIs already expose compression options. Document the raw cache, base panel, factor store, and artifact defaults. Add tests for invalid compression-level combinations and explicit row group propagation.

Rationale: The source already defaults to `zstd`; the remaining gap is consistent control and clear docs.

Alternative considered: make a broad storage migration part of this change. That would increase risk and is not required for new writes.

## Risks / Trade-offs

- External factor-store output can still require substantial memory because DolphinDB calculation remains full-range in the first version. Mitigation: keep factor dtype default at `float32`, write partitions immediately after validation, and defer chunked DolphinDB computation until overlap semantics are designed.
- Loading a large base panel for status can be slow. Mitigation: make the command explicit through `--panel`, keep raw cache summaries manifest-based, and reserve deeper audits for later options.
- Factor store manifests may not contain enough metadata for all desired status fields. Mitigation: report unknown fields explicitly and extend manifest metadata as writers are updated.
- Docker compose depends on DolphinDB image tags, module paths, and licensing outside this repository. Mitigation: document placeholders and keep compose as an integration scaffold rather than a hidden dependency.
- Adding multiple CLI options can create inconsistent behavior if each parser handles validation differently. Mitigation: route parquet options through shared helper functions and cover parser-level behavior in tests.

## Migration Plan

1. Add `data_quality`, `data_status`, and the `moneytrees-data-status` CLI without changing existing TuShare outputs.
2. Update TuShare to call the shared quality wrapper while preserving `--sanity-check off|warn|error` behavior.
3. Refactor factor-store partition writing and add external Alpha101/191 factor-store output to the DolphinDB CLI.
4. Add Dockerfile and compose files after the runtime commands are stable.
5. Add `docs/data_status.md`, update DolphinDB docs, and link from README.
6. Add missing parquet option exposure and tests.

Rollback is straightforward for each step because the change is additive: remove the new CLI entry point, stop using `--factor-store-output`, or ignore Docker/compose files. Existing wide-panel workflows remain available.

## Open Questions

- Which DolphinDB image tag and module mount convention should become the documented default?
- Should data-status include an optional heavy audit mode that reads all factor partitions, or should that become a separate `data-audit` command later?
- Should `moneytrees-factor-store` eventually accept precomputed external family files directly, or should that remain owned by `moneytrees-dolphindb-alphas`?
- Should artifacts status be limited to known Money Trees manifests and metrics, or include generic size and freshness summaries for any artifact directory?
