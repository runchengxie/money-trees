## ADDED Requirements

### Requirement: CN market profile validates and normalizes CN benchmark data
The system SHALL provide a runnable `cn` market profile that validates the CN dataset contract and normalizes benchmark inputs into canonical benchmark columns used by the backtest core.

#### Scenario: CN dataset uses benchmark aliases
- **WHEN** a CN dataset includes the configured benchmark return and cumulative benchmark columns
- **THEN** the `cn` market profile normalizes them into canonical benchmark fields required by downstream code

#### Scenario: CN dataset is missing required benchmark data
- **WHEN** the `cn` market profile receives a dataset without the benchmark fields required for the configured label source
- **THEN** the system fails fast with a validation error that identifies the missing columns

### Requirement: CN market profile applies tradability constraints
The system SHALL allow the `cn` market profile to filter rows using CN tradability inputs for suspension, ST treatment, and limit-hit conditions.

#### Scenario: Suspended names are excluded
- **WHEN** a CN test or backtest window contains rows marked as suspended
- **THEN** the tradability filter excludes those rows from model fitting and evaluation slices that require tradable names

#### Scenario: ST names are excluded when configured
- **WHEN** the CN market configuration marks ST filtering as enabled and rows are flagged as ST
- **THEN** the tradability filter excludes those rows from CN train, validation, holdout, and rolling test slices

#### Scenario: Limit-hit names are excluded
- **WHEN** CN rows are flagged as locked at the configured up-limit or down-limit condition
- **THEN** the tradability filter excludes those rows from evaluation slices that represent executable portfolio formation

### Requirement: CN market config runs through the standard CLI
The system SHALL allow a CN market config to run through the existing CLI and config stacking flow without requiring a separate entry point.

#### Scenario: CN config stack is provided to the CLI
- **WHEN** the user runs the standard backtest CLI with a CN market config and a dataset that satisfies the CN contract
- **THEN** the run completes and produces the same categories of artifacts as a US run
