## Why

The repository already contains a reusable cross-sectional backtest scaffold, but only the `us` market profile is runnable and many evaluation/reporting paths still assume SPY semantics. To make the project usable for A-share research, the codebase needs a first-class CN market path with explicit tradability rules and benchmark-neutral interfaces.

## What Changes

- Add a runnable `cn` market profile instead of the current placeholder implementation.
- Define CN-specific required columns, frame preparation rules, and tradability filtering for suspension, ST treatment, and limit-hit names.
- Generalize benchmark handling so the backtest, metrics, outputs, and summaries use benchmark-neutral naming instead of SPY-specific assumptions.
- Add a CN baseline config path that can run through the existing CLI and produce comparable artifacts.
- Expand tests to cover CN market preparation, tradability behavior, and benchmark-agnostic reporting/output generation.

## Capabilities

### New Capabilities
- `cn-market-profile`: Run the template with an A-share/CN market profile that validates CN data contracts and applies CN tradability constraints.
- `benchmark-agnostic-reporting`: Produce backtest outputs and metrics against a configured benchmark without hard-coding SPY-specific labels or filenames.

### Modified Capabilities

None.

## Impact

- Affected code: `src/treealpha/markets/`, `src/treealpha/data.py`, `src/treealpha/backtest.py`, `src/treealpha/runner.py`, `src/treealpha/config.py`, `src/treealpha/cli/`.
- Affected configs: `configs/market/cn.yaml` and new/updated smoke coverage for CN scenarios.
- Affected outputs: benchmark series naming in CSV/JSON/text summaries and run metadata.
- Affected tests: market profile tests, CLI/backtest integration tests, and output assertions.
