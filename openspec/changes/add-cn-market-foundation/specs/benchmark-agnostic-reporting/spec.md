## ADDED Requirements

### Requirement: Backtest metrics use canonical benchmark inputs
The system SHALL compute benchmark-relative metrics from canonical benchmark series rather than from SPY-specific field names.

#### Scenario: Canonical benchmark fields are present
- **WHEN** the backtest runner receives a processed frame with canonical benchmark columns
- **THEN** the benchmark series builder and performance metrics use those fields to compute benchmark-relative outputs

#### Scenario: A non-US benchmark is configured
- **WHEN** a market config identifies a benchmark other than SPY
- **THEN** the run summary and metrics compare the strategy against the configured benchmark instead of referring to SPY

### Requirement: Runner emits benchmark-neutral artifacts
The system SHALL emit benchmark-neutral output artifacts for benchmark NAV, benchmark returns, and strategy-versus-benchmark comparisons.

#### Scenario: A backtest run completes
- **WHEN** the runner writes output artifacts for a completed run
- **THEN** it writes benchmark-neutral comparison files and metadata instead of relying only on SPY-named filenames

#### Scenario: Holdout artifacts are written
- **WHEN** the runner exports holdout results
- **THEN** it writes the holdout benchmark series and benchmark comparison artifacts using the same benchmark-neutral naming scheme

### Requirement: US runs preserve a backward-compatible SPY bridge
The system SHALL preserve a backward-compatible SPY alias layer for US runs during the initial benchmark-neutral migration.

#### Scenario: US run writes outputs
- **WHEN** the configured market profile is `us`
- **THEN** the runner continues to expose SPY-named aliases for existing consumers while also producing canonical benchmark artifacts
