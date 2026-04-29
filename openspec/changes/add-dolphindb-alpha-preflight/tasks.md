## 1. Test Coverage

- [x] 1.1 Extend the mocked DolphinDB session in `tests/test_build_dolphindb_alphas_script.py` so tests can simulate successful preflight, missing modules, and missing wrapper functions.
- [x] 1.2 Add tests that Alpha101 preflight loads `wq101alpha`, `prepare101`, and `moneytreeAlpha` before generation.
- [x] 1.3 Add tests that Alpha191 preflight loads `gtja191Alpha`, `gtja191Prepare`, and `moneytreeAlpha` before generation.
- [x] 1.4 Add tests that missing module failures raise an actionable error naming the failed module, expected `.dos` file, and `docker/dolphindb/modules/`.
- [x] 1.5 Add tests that missing wrapper function failures name the configured Alpha101 or Alpha191 wrapper function.
- [x] 1.6 Add tests that custom `--alpha101-function` and `--alpha191-function` names are used by preflight.

## 2. CLI Preflight Implementation

- [x] 2.1 Add helper functions in `src/moneytree/cli/dolphindb_alphas.py` to derive required DolphinDB modules from selected families.
- [x] 2.2 Add a preflight function that runs simple `use <module>` checks and raises a clear Money Trees error when DolphinDB rejects a module.
- [x] 2.3 Add a wrapper-function preflight check for the selected family functions from `--alpha101-function` and `--alpha191-function`.
- [x] 2.4 Call preflight after connecting to DolphinDB and before loading or generating Alpha101/191 factors.
- [x] 2.5 Ensure preflight errors explain that `--wq101-module-version`, `--gtja191-module-version`, and `--moneytree-alpha-module-version` are manifest metadata and do not change DolphinDB module names.
- [x] 2.6 Decide whether to add `--skip-preflight`; if added, document it as an explicit compatibility escape hatch and cover it with a test.

## 3. Documentation

- [x] 3.1 Update `docs/dolphindb_alpha101_191.md` with the required local `.dos` file list, repository Docker module mount path, and standalone module-loading verification command.
- [x] 3.2 Update `docs/dolphindb_alpha101_191.md` with the staged execution sequence: run `--alpha101`, then `--alpha191`, then both into factor store.
- [x] 3.3 Update `docs/runbook.md` troubleshooting so missing-module and missing-wrapper failures point to the new preflight diagnostics.
- [x] 3.4 Reaffirm in docs that third-party DolphinDB formula modules and production `moneytreeAlpha.dos` wrappers are local runtime inputs and are not committed to the repository.

## 4. Verification

- [x] 4.1 Run `uv run pytest -q tests/test_build_dolphindb_alphas_script.py tests/test_external_alphas.py`.
- [x] 4.2 Run `uv run ruff check src/moneytree/cli/dolphindb_alphas.py tests/test_build_dolphindb_alphas_script.py`.
- [ ] 4.3 Manually verify the documented standalone DolphinDB module-loading command against a local server when the `.dos` modules are available. Blocked locally because `docker/dolphindb/modules/` only contains `.gitkeep`.
