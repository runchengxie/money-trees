## Why

Generating Alpha101/191 currently fails late with raw DolphinDB parser errors when required server-side `.dos` modules or Money Trees wrapper functions are missing. Users need a clear, staged path that separates local DolphinDB environment setup from Money Trees CLI behavior before uploading large panels or writing factor-store output.

## What Changes

- Add a DolphinDB Alpha101/191 preflight path that validates required server modules before generation.
- Validate the Money Trees wrapper module exposes the expected Alpha101/191 entrypoints for the requested families.
- Report actionable errors that name missing modules, missing wrapper functions, and the expected local module directory.
- Document the recommended step-by-step recovery flow: install external modules, validate loading, run Alpha101 alone, run Alpha191 alone, then run both into factor store.
- Preserve the current external-alpha boundary: third-party DolphinDB formula modules and local `.dos` wrappers are not committed to the repository.
- Keep the existing `moneytrees-dolphindb-alphas` generation behavior compatible after preflight passes.

## Capabilities

### New Capabilities

- `dolphindb-alpha-preflight`: Validate DolphinDB Alpha101/191 server modules and Money Trees wrapper functions before running external-alpha generation.

### Modified Capabilities

None.

## Impact

- Affected CLI: `src/moneytree/cli/dolphindb_alphas.py`.
- Affected docs: DolphinDB Alpha101/191 runbook and related troubleshooting docs.
- Affected tests: DolphinDB external-alpha CLI tests should cover successful preflight, missing module diagnostics, and missing wrapper function diagnostics.
- No new core dependency is introduced; DolphinDB remains an optional external-alpha dependency.
