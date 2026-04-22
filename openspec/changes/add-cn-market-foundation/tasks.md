## 1. CN market profile and config plumbing

- [x] 1.1 Extend config loading so runtime settings carry the configured benchmark label plus CN tradability column mappings and filter toggles.
- [x] 1.2 Replace the placeholder `CNMarketProfile` with a runnable implementation of `required_columns`, `prepare_frame`, and `filter_tradable_frame`.
- [x] 1.3 Add or update CN market config fixtures so a CN config stack can run through the existing CLI without a separate entry point.

## 2. Benchmark-neutral backtest and reporting

- [x] 2.1 Canonicalize benchmark handling in the data/backtest path around `benchmark_next_period_return` and `benchmark_cum_ret` while keeping US `spy_*` aliases readable.
- [x] 2.2 Update runner summaries, metrics labels, and holdout reporting to reference the configured benchmark instead of hard-coded SPY wording.
- [x] 2.3 Emit benchmark-neutral output artifacts and preserve SPY-named compatibility aliases for US runs during the migration bridge.

## 3. Validation, regression coverage, and docs

- [x] 3.1 Add unit tests for CN dataset validation, benchmark normalization, and tradability filtering of suspended, ST, and limit-hit rows.
- [x] 3.2 Add integration or smoke coverage for a CN config stack that exercises the standard CLI and verifies benchmark-neutral artifacts.
- [x] 3.3 Update README/examples to document the CN market contract, benchmark-neutral outputs, and the temporary SPY compatibility bridge.
