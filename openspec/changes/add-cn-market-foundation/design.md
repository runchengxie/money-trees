## Context

The repository is a cross-sectional equity backtest template with separable market, model, and backtest configs. The current architecture already has a `BaseMarketProfile` abstraction and a registered `cn` profile, but the CN implementation is still a placeholder and the backtest/reporting flow remains tied to SPY-centric naming in several places.

This change is cross-cutting because CN support touches market validation, preprocessing, benchmark handling, summaries, output filenames, and integration tests. The goal is to make CN a real runnable path without turning the project into a larger multi-market platform rewrite.

## Goals / Non-Goals

**Goals:**

- Make `configs/market/cn.yaml` usable with a concrete `CNMarketProfile`.
- Normalize CN inputs into the same benchmark and return contracts expected by the backtest core.
- Replace hard-coded SPY semantics in the evaluation/output path with benchmark-neutral behavior.
- Preserve the current CLI and config stacking workflow.
- Add regression coverage so CN and US paths both remain runnable.

**Non-Goals:**

- Adding new model families or changing the model adapter contract.
- Introducing PIT fundamentals, long-only portfolio rules, or board-specific universe builders.
- Redesigning the entire config system around nested market/provider plugins.
- Removing US compatibility or breaking existing US smoke paths outright.

## Decisions

### Decision: Keep market-specific behavior inside market profiles

The project already isolates market logic behind `BaseMarketProfile`. We will implement CN support by expanding that layer rather than creating a new pipeline fork or a parallel CN package.

Why:

- It matches the current code structure.
- It keeps the change small enough to implement in one iteration.
- It avoids duplicating backtest and runner logic.

Alternative considered:

- Add a new `market_rules/` subsystem now.
  Rejected because the repository is still small and the immediate need is a concrete CN implementation, not a larger abstraction pass.

### Decision: Use canonical `benchmark_*` fields internally

The data/preprocessing/backtest stack will treat `benchmark_next_period_return` and `benchmark_cum_ret` as the canonical benchmark columns. US alias handling for `spy_*` remains supported as an input/output compatibility layer.

Why:

- CN support should not introduce a second benchmark convention.
- Canonical benchmark fields simplify metrics, summaries, and output logic.
- The data module already partially supports these aliases, so this is an extension of the existing direction.

Alternatives considered:

- Keep separate SPY and CN code paths.
  Rejected because it would preserve current naming debt and make every new market more expensive.

### Decision: Make tradability filters configurable but implemented in CN profile

The CN profile will read configured tradability columns and apply filtering for suspension, ST status, and limit-hit conditions. Missing configured columns will fail fast when CN semantics require them.

Why:

- The config already hints at these fields.
- A-share execution assumptions differ from the US reference path and must be explicit.
- Failing fast is safer than silently running a misleading CN backtest.

Alternatives considered:

- Infer tradability only from generic `is_tradable`.
  Rejected because it hides the exact A-share assumptions and makes debugging harder.

### Decision: Introduce benchmark-neutral artifacts while keeping a short compatibility bridge

The runner will emit canonical benchmark artifacts such as benchmark NAV/returns and benchmark comparison tables. For the US path, legacy SPY-named aliases can continue to be emitted for compatibility until downstream users migrate.

Why:

- It lets CN land cleanly.
- It reduces churn for the existing US template behavior.
- It creates a clear path to deprecate SPY-only names later.

Alternatives considered:

- Rename all artifacts immediately with no compatibility layer.
  Rejected because the project already has tests and user expectations tied to SPY filenames.

## Risks / Trade-offs

- [CN data contracts differ across users] → Mitigation: make tradability column names configurable and validate them explicitly in the profile.
- [Benchmark-neutral renaming can break existing consumers] → Mitigation: emit canonical files first and preserve SPY aliases for US compatibility during this change.
- [CN support may encourage over-scoping into target/model redesign] → Mitigation: keep this change limited to market/profile and benchmark/reporting foundation.
- [Synthetic tests may miss real data edge cases] → Mitigation: add unit tests for normalization/filtering logic and at least one CLI-style integration test for CN.

## Migration Plan

1. Implement `CNMarketProfile` and benchmark canonicalization while preserving US behavior.
2. Update runner/backtest outputs and summary text to use configured benchmark naming.
3. Add or update tests to cover CN preprocessing, tradability filtering, and benchmark-neutral artifacts.
4. Keep legacy SPY aliases for the US path during this change so existing smoke coverage and downstream tooling remain functional.

Rollback strategy:

- Revert the benchmark-neutral artifact rename logic while retaining the CN profile work if downstream compatibility issues appear.
- Revert the CN profile independently if data contract assumptions prove incorrect.

## Open Questions

- Should ST names always be excluded in the first CN implementation, or should that remain a config toggle with a stricter default?
- Do we want canonical benchmark filenames only, or canonical plus legacy aliases for every market during a deprecation period?
- Should the first CN smoke dataset represent only long/short feasibility, or also include explicit suspension and limit-hit examples?
