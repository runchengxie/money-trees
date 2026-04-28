## ADDED Requirements

### Requirement: Data status CLI entry point
The system SHALL provide `moneytree-data-status` and `moneytrees-data-status` console scripts that run a read-only status report over explicitly provided data layers.

#### Scenario: Status command is registered
- **WHEN** the project scripts are inspected
- **THEN** both `moneytree-data-status` and `moneytrees-data-status` resolve to the same CLI module

#### Scenario: No layer is provided
- **WHEN** the user runs `moneytrees-data-status` without `--panel`, `--raw-cache`, `--factor-store`, or `--artifacts`
- **THEN** the command exits with an argument error explaining that at least one data layer path is required

### Requirement: Base panel status
The data status command SHALL report base panel coverage and quality for a provided `date, ticker` panel without mutating the panel file.

#### Scenario: Valid base panel is inspected
- **WHEN** the user runs `moneytrees-data-status --panel <path>`
- **THEN** the output includes row count, column count, date range, date count, ticker count, duplicate key count, required column status, null rates, and file size

#### Scenario: Duplicate base panel keys are present
- **WHEN** the panel contains duplicate `date, ticker` keys and the user runs with `--mode error`
- **THEN** the command reports the duplicate key count and exits non-zero

### Requirement: Shared data quality rules
Panel quality checks SHALL be implemented in a shared module so TuShare sanity checks and data status use the same required-column, null-rate, duplicate-key, price, volume, and OHLC rules.

#### Scenario: TuShare sanity reuses shared rules
- **WHEN** `moneytrees-tushare --sanity-check error` checks a standardized panel with duplicated `date, ticker` keys
- **THEN** the command fails through the shared data quality rule instead of a TuShare-only implementation

#### Scenario: Warn mode does not fail the command
- **WHEN** shared data quality detects warnings and the selected mode is `warn`
- **THEN** warnings are rendered but the command does not fail because of warnings alone

### Requirement: Raw cache manifest status
The data status command SHALL summarize a TuShare raw cache by reading `manifest.sqlite` and grouping rows by source and API name.

#### Scenario: Raw cache manifest exists
- **WHEN** the user runs `moneytrees-data-status --raw-cache data/raw/tushare`
- **THEN** the output includes manifest existence, API names, date ranges, shard counts, row counts, schema hash counts, and content hash counts

#### Scenario: Raw cache manifest is missing
- **WHEN** the raw cache directory does not contain `manifest.sqlite`
- **THEN** the output reports the raw cache layer as missing and `--mode error` exits non-zero

### Requirement: Factor store status
The data status command SHALL summarize a Money Trees factor-store manifest and report base panel metadata, factor families, column counts, partition counts, rows, and alignment state.

#### Scenario: Factor store manifest exists
- **WHEN** the user runs `moneytrees-data-status --factor-store data/factor_store/cn`
- **THEN** the output includes the manifest path, base panel rows and columns, factor family names, each family prefix, each family column count, each family row count, and each family partition count

#### Scenario: Requested factor store is malformed
- **WHEN** the factor-store manifest is missing required keys or points to missing factor files
- **THEN** the output reports factor-store errors and `--mode error` exits non-zero

### Requirement: Artifact status
The data status command SHALL summarize known Money Trees artifact directories without reading raw data or generated parquet contents.

#### Scenario: Artifact directory is inspected
- **WHEN** the user runs `moneytrees-data-status --artifacts artifacts/<run>`
- **THEN** the output reports whether known files such as `experiment_manifest.json`, metrics files, run config files, and exported parquet files are present, plus total size where available

### Requirement: Text and JSON output
The data status command SHALL support `--format text` and `--format json` with equivalent status content.

#### Scenario: JSON output is selected
- **WHEN** the user runs `moneytrees-data-status --panel <path> --format json`
- **THEN** stdout contains a JSON object with machine-readable layer status and issue lists

#### Scenario: Text output is selected
- **WHEN** the user runs `moneytrees-data-status --panel <path> --format text`
- **THEN** stdout contains a human-readable summary suitable for terminal use

### Requirement: Read-only behavior
The data status command MUST NOT delete, rewrite, compact, refresh, repair, or create runtime data files.

#### Scenario: Status command completes
- **WHEN** `moneytrees-data-status` finishes successfully or with reported errors
- **THEN** input panel files, raw cache parquet files, raw cache manifests, factor-store files, and artifacts remain unmodified
