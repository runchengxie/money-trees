## 1. Audit and Classification

- [x] 1.1 Update `docs/maintenance.md` with current line-count evidence for oversized modules and the intended split direction.
- [x] 1.2 Add a compatibility lifecycle table covering script wrappers, pickle migration, notebook compatibility presets, CLI aliases, and `moneytree.factors.ops`.
- [x] 1.3 Classify each compatibility surface as `active`, `compatibility`, `deprecated`, or `removal-candidate`.
- [x] 1.4 Record replacement guidance for every item marked `deprecated` or `removal-candidate`.

## 2. Legacy Entry Points

- [x] 2.1 Decide whether `scripts/convert_pickle_to_parquet.py` remains as a compatibility helper or points users to `moneytrees-parquet-rewrite`.
- [x] 2.2 Add or update tests for the chosen pickle migration path and warning or migration text.
- [x] 2.3 Decide whether `scripts/build_dolphindb_alphas.py` emits a deprecation notice or remains a silent compatibility wrapper.
- [x] 2.4 Preserve tests proving the DolphinDB wrapper still delegates to `moneytree.cli.dolphindb_alphas`.
- [x] 2.5 Decide whether `configs/preset/notebook_compat.yaml` remains a permanent alias or receives deprecation guidance.
- [x] 2.6 Update configuration docs and tests for the chosen notebook compatibility preset lifecycle.

## 3. Runner Refactor

- [x] 3.1 Extract output-writing helpers from `src/moneytree/runner.py` into a cohesive internal module.
- [x] 3.2 Extract holdout evaluation helpers from `src/moneytree/runner.py` into a cohesive internal module.
- [x] 3.3 Extract run summary and report text helpers from `src/moneytree/runner.py` into a cohesive internal module.
- [x] 3.4 Keep `moneytree.runner.run_backtest()` and existing CLI behavior source-compatible.
- [x] 3.5 Add or update focused tests covering output files, holdout metrics, and run summary contents.

## 4. Factor Store Refactor

- [x] 4.1 Extract manifest schema creation, reading, and compatibility checks from `src/moneytree/factor_store.py`.
- [x] 4.2 Extract factor-store key and schema validation helpers from `src/moneytree/factor_store.py`.
- [x] 4.3 Keep imports from `moneytree.factor_store` compatible for writer, loader, validation, and memory-estimation functions.
- [x] 4.4 Add or update tests covering manifest compatibility, selected family loading, partition pruning, and mismatch errors.
- [x] 4.5 Document any remaining writer, loader, or partitioning split as follow-up work if it is not completed in this change.

## 5. Utility and Quality Gates

- [x] 5.1 Audit `src/moneytree/factors/ops.py` references and decide whether it is internal-only or part of the public factor API.
- [x] 5.2 Update tests and `__all__` or documentation to match the chosen `factors.ops` status.
- [x] 5.3 Evaluate Ruff rules for complexity and simplification, and document which are enforced now versus deferred.
- [x] 5.4 Fix long or dense touched lines in refactored modules where doing so improves readability without unrelated churn.

## 6. Verification

- [x] 6.1 Run `uv run ruff check .`.
- [x] 6.2 Run `uv run pytest -q tests/test_factor_store.py tests/test_backtest_cli.py tests/test_build_dolphindb_alphas_script.py tests/test_convert_pickle_to_parquet_script.py tests/test_factors.py`.
- [x] 6.3 Run `uv run pytest -q`.
- [x] 6.4 Update docs if verification changes the recommended implementation order or compatibility lifecycle.
