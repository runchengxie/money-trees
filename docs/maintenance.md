# Maintenance backlog

[简体中文](https://runchengxie.github.io/money-trees/zh-CN/maintenance/)

This document records module boundaries that are worth improving but should not be refactored without a clear need. It is not the primary operations runbook. Before a substantial refactor, write or update the corresponding design note or implementation plan.

Line counts below were checked on 2026-10-01. The backlog focuses on core modules with mixed responsibilities, broad test surfaces, or frequent changes; it does not require rewriting them wholesale.

## Large modules and responsibility boundaries

| File | Lines (2026-10-01) | Current concern | Follow-up |
| --- | ---: | --- | --- |
| `src/moneytree/factor_store.py` | 2020 | Local/external factor stores, partitioning, compression, schema validation, and loading remain concentrated here. Manifest and validation concerns have partly moved to separate modules. | Further separate partitioning, local and external writers, and I/O helpers while keeping the `moneytree.factor_store` facade. |
| `src/moneytree/runner.py` | 878 | Backtest orchestration remains concentrated. Output writing, holdout evaluation, and summary generation have partly moved to separate modules. | Continue decomposing orchestration while preserving the `run_backtest()` entry point. |
| `src/moneytree/data_sources/tushare.py` | 1069 | TuShare client, raw cache, normalization, and manifest migration are combined. | Separate client, cache, standardization, and manifest-migration responsibilities. |
| `src/moneytree/data.py` | 880 | Data loading, index normalization, label generation, feature selection, and missing-value policy are combined. | Organize around loading, labels, feature policy, and index helpers. |
| `src/moneytree/cli/dolphindb_alphas.py` | 826 | CLI arguments, DolphinDB orchestration, streaming, output validation, and manifest generation are combined. | Separate argument validation, streamed generation, and output validation. |
| `src/moneytree/data_status.py` | 822 | Status inspection and rendering for panels, raw cache, factor stores, and backtest artifacts are combined. | Separate layer inspectors, quality checks, and renderers. |
| `src/moneytree/backtest.py` | 688 | Rolling windows, metrics, diagnostics, and series assembly are combined. | Separate metrics, rolling, and diagnostics while preserving public re-exports. |
| `src/moneytree/portfolio.py` | 657 | Heuristic weights, QP, covariance estimation, and constraints are combined. | Separate portfolio configuration, heuristic logic, QP, and risk/covariance helpers. |
| `src/moneytree/model.py` | 707 | Random-forest utilities, scoring, tuning, feature selection, and legacy notebook behavior are combined. | Separate scoring, model selection, random-forest tuning, and legacy compatibility. |
| `src/moneytree/factors/external.py` | 424 | External Alpha field mapping, validation, merging, and manifest logic are combined. | Consider separating field mapping, validation, and manifest helpers. |

## Historical and compatibility tools

Lifecycle labels:

- `active`: supported path; documentation and new examples may use it.
- `compatibility`: retained for compatibility, but not preferred in new documentation.
- `deprecated`: a replacement exists; the old path remains available temporarily with migration guidance.
- `removal-candidate`: remove only after confirming there are no tests or external compatibility commitments.

| Item | Status | Evidence | Recommended path |
| --- | --- | --- | --- |
| `scripts/convert_pickle_to_parquet.py` | `deprecated` | Handles only migration from trusted pickle to parquet. The data contract recommends `moneytrees-parquet-rewrite`. | Use `uv run moneytrees-parquet-rewrite --input old.pkl --output old.parquet`. |
| `scripts/build_dolphindb_alphas.py` | `compatibility` | Tests confirm it delegates to `moneytree.cli.dolphindb_alphas`; external scripts may still use the old path. | Use `moneytrees-dolphindb-alphas`. |
| `configs/preset/notebook_compat.yaml` | `deprecated` | Matches `legacy_notebook_compat.yaml` but remains a transitional alias. | Use `configs/preset/legacy_notebook_compat.yaml` to reproduce early notebooks. |
| `configs/preset/legacy_notebook_compat.yaml` | `compatibility` | Explicitly for reproducing early notebooks, not the default research path. | For formal research, use the base market and model configurations. |
| Singular `moneytree*` CLI aliases | `compatibility` | `pyproject.toml` and tests retain the aliases to avoid breaking existing commands. | Prefer `moneytrees*` in new documentation. |
| Pickle input | `compatibility` | The data contract permits trusted legacy inputs, but recommends parquet. | Migrate to parquet or use a factor-store input. |
| Legacy notebook model path | `compatibility` | The `notebook_compat` feature-selection and tuning paths remain covered by tests. | Use the default feature lag, missing-feature policy, and configuration stack for new experiments. |
| `moneytree.factors.ops` | `compatibility` | Tests cover this submodule, but it is not exported from the top-level `moneytree.factors` package. | Keep it as an internal operator helper. Use factor-family builders and IC functions exported from `moneytree.factors` as the public API. |

## Suggested decomposition order

1. `runner.py`: continue separating orchestration stages while keeping `run_backtest()` stable.
2. `factor_store.py`: finish separating partitioning, writers, and loading after the manifest and validation helpers already extracted.
3. `backtest.py`: separate metrics, rolling logic, and diagnostics while preserving public re-exports.
4. `portfolio.py`: separate heuristic logic, QP, risk/covariance, and diagnostics.
5. `model.py`: move legacy random-forest free functions behind a compatibility facade.
6. `data_sources/tushare.py`: separate client, cache, fetch, standardization, and panel assembly.

As of 2026-10-01, runner output writing, holdout evaluation, and summary generation, plus factor-store manifest and validation helpers, are handled by separate modules. Factor-store writers, loaders, and partitioning remain follow-up areas. Preserve the `moneytree.factor_store` facade as they are separated.

## Quality gates

For routine changes, run:

```bash
uv run ruff check .
uv run pytest -q
```

Changes to TuShare, DolphinDB, model adapters, configuration parsing, output files, or data contracts should include the relevant focused tests.

Ruff currently enables `E/F/I/UP/B`; `line-length = 100` and `E501` is globally ignored. For touched modules, clean up obvious long or dense expressions without mechanically reformatting unrelated files. Candidate rules remain staged:

| Rule | Status | Notes |
| --- | --- | --- |
| `C90` | Backlog | Use to identify high cyclomatic complexity, starting with `runner.py`, `factor_store.py`, and `portfolio.py`. |
| `SIM` | Backlog | Simplify branches and expressions incrementally after module boundaries are clearer. |
| `RET` | Backlog | Clean up return style selectively; do not enable repository-wide yet. |
| `ARG` | Backlog | Review unused arguments carefully around CLI callbacks, test fixtures, and compatibility facades. |
| `E501` | Scoped | Continue to ignore globally; follow the 100-character intent in files being changed. |
