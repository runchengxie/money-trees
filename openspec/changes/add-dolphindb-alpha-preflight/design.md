## Context

`moneytrees-dolphindb-alphas` uploads the normalized Money Trees panel to DolphinDB, runs a setup script with `use wq101alpha`, `use prepare101`, `use gtja191Alpha`, `use gtja191Prepare`, and `use moneytreeAlpha`, then calls `calcMoneyTreeAlpha101` and/or `calcMoneyTreeAlpha191`. When any server-side module is missing, DolphinDB raises a low-level parser/runtime error after the Python process has already loaded the input panel and connected to the server.

The external Alpha101/191 boundary is intentional: the repository owns the Python CLI, validation, manifests, documentation, and the Money Trees output contract, but it does not vendor third-party DolphinDB formula modules or local proprietary wrapper code. The fix should therefore improve preflight validation and operator guidance without changing factor formulas or introducing DolphinDB as a core dependency.

## Goals / Non-Goals

**Goals:**

- Fail early with explicit diagnostics for missing DolphinDB modules required by the selected families.
- Validate that `moneytreeAlpha` exposes the wrapper functions needed by the selected families.
- Make the operator recovery flow clear: install modules, verify loading, run Alpha101, run Alpha191, then run both into factor store.
- Keep existing successful generation behavior and output contracts unchanged.
- Keep tests independent of a real DolphinDB server by using mocked sessions.

**Non-Goals:**

- Do not commit `wq101alpha.dos`, `prepare101.dos`, `gtja191Alpha.dos`, `gtja191Prepare.dos`, or production `moneytreeAlpha.dos`.
- Do not reimplement Alpha101/191 formulas in Python.
- Do not change the factor-store layout, Alpha101/191 column names, or manifest schema beyond any optional preflight metadata that is useful for diagnostics.
- Do not make DolphinDB a required dependency for normal `moneytrees` backtests.

## Decisions

1. Add a preflight helper in `src/moneytree/cli/dolphindb_alphas.py`.

   The helper will derive required modules from selected families and run small DolphinDB scripts before loading and generating factors. For Alpha101 it checks `wq101alpha`, `prepare101`, and `moneytreeAlpha`; for Alpha191 it checks `gtja191Alpha`, `gtja191Prepare`, and `moneytreeAlpha`. This keeps validation close to the CLI behavior that depends on it.

   Alternative considered: document-only fix. That would help the immediate case but would keep future failures as raw DolphinDB errors, so it does not address the late-failure behavior.

2. Surface a Money Trees exception with actionable text.

   The CLI should catch DolphinDB errors during preflight and raise a clear Python-side error naming the missing or failed module/function, the expected file names under `docker/dolphindb/modules/`, and the fact that `--*-module-version` records manifest metadata rather than changing module names.

   Alternative considered: let DolphinDB exceptions propagate. That preserves raw detail but forces users to infer repository-specific setup from a server parser error.

3. Validate wrapper functions separately from module loading.

   After `use moneytreeAlpha`, preflight should check the requested wrapper function names from `--alpha101-function` and `--alpha191-function`. The exact DolphinDB probe can be implementation-specific, but tests should verify the emitted script references the configured function names and turns failure into an actionable message.

   Alternative considered: wait until generation calls the functions. That catches the issue eventually, but only after setup and input upload have completed.

4. Make preflight the default for generation without adding a `--skip-preflight` flag initially.

   The common case benefits from early failure, and the first implementation uses simple module loading plus `defs()` function lookup. If a real DolphinDB version compatibility issue appears later, a `--skip-preflight` flag can be proposed as an explicit operator escape hatch.

## Risks / Trade-offs

- Preflight probes may differ across DolphinDB versions -> keep probes simple, test the generated scripts, and document `--skip-preflight` if introduced.
- Module loading can still fail later if a module has internal runtime issues -> preflight will only guarantee module/function availability, not formula correctness.
- Error parsing from DolphinDB can be brittle -> avoid deep parser-error interpretation; include the failing module/function from Money Trees' own preflight step.
- Extra server round trips add small latency -> acceptable because it prevents expensive panel upload/generation failures and only applies to external-alpha generation.

## Migration Plan

Existing commands continue to work. Users with complete DolphinDB module installations see no behavior change except a short preflight before generation. Users with incomplete installations receive an earlier, clearer error and follow the documented recovery sequence.

No data migration is required.

## Open Questions

- Should successful preflight details be recorded in the external-alpha manifest, or should manifests remain focused on generation inputs and module version metadata?
