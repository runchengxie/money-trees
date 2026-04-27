## ADDED Requirements

### Requirement: External Alpha Family Contract
The system SHALL define Alpha101 and Alpha191 as externally produced factor families with exact canonical column sets.

#### Scenario: Alpha101 canonical columns are requested
- **WHEN** the external alpha contract is asked for the Alpha101 column set
- **THEN** it returns exactly 101 columns named `alpha101_001` through `alpha101_101`

#### Scenario: Alpha191 canonical columns are requested
- **WHEN** the external alpha contract is asked for the Alpha191 column set
- **THEN** it returns exactly 191 columns named `alpha191_001` through `alpha191_191`

#### Scenario: Unsupported external family is requested
- **WHEN** the external alpha contract is asked for an unsupported family
- **THEN** the system rejects the request with a clear error listing supported external families

### Requirement: External Alpha Input Mapping
The system SHALL map the standard `date, ticker` panel into the DolphinDB input schema using explicit, documented field selection rules.

#### Scenario: Adjusted price fields are available
- **WHEN** the input panel contains `open_adj`, `high_adj`, `low_adj`, `close_adj`, and `vwap_adj`
- **THEN** the DolphinDB input uses those adjusted price fields for `open`, `high`, `low`, `close`, and `vwap`

#### Scenario: Adjusted price fields are unavailable
- **WHEN** an adjusted price field is missing and its raw field exists
- **THEN** the DolphinDB input falls back to the raw field and records the selected field in the manifest

#### Scenario: Volume field is available
- **WHEN** the input panel contains `volume`
- **THEN** the DolphinDB input uses `volume` as `vol`

#### Scenario: TuShare vol fallback is required
- **WHEN** the input panel lacks `volume` but contains TuShare `vol`
- **THEN** the DolphinDB input derives `vol` as `vol * 100` and records the fallback in the manifest

#### Scenario: Required Alpha191 benchmark fields are missing
- **WHEN** Alpha191 generation is requested and the input panel lacks required benchmark open or close fields
- **THEN** the system fails before calling DolphinDB with a clear missing-field error

### Requirement: DolphinDB External Alpha Generation
The system SHALL provide an offline command or script that connects to DolphinDB, generates requested Alpha101 and Alpha191 columns, and merges the results into the input panel.

#### Scenario: Alpha101 generation succeeds
- **WHEN** the user runs the external alpha command with Alpha101 enabled and DolphinDB returns a valid Alpha101 result table
- **THEN** the output parquet contains the original panel columns plus exactly the canonical Alpha101 columns

#### Scenario: Alpha191 generation succeeds
- **WHEN** the user runs the external alpha command with Alpha191 enabled and DolphinDB returns a valid Alpha191 result table
- **THEN** the output parquet contains the original panel columns plus exactly the canonical Alpha191 columns

#### Scenario: Multiple external families are requested
- **WHEN** the user requests both Alpha101 and Alpha191
- **THEN** the output parquet contains both canonical column sets merged on `date, ticker`

#### Scenario: DolphinDB client is not installed
- **WHEN** the user runs the external alpha command without the optional DolphinDB Python client installed
- **THEN** the command exits with a clear installation message and does not create partial output

### Requirement: External Alpha Validation
The system SHALL validate external alpha outputs before writing the merged parquet.

#### Scenario: Duplicate input keys exist
- **WHEN** the input panel contains duplicate `date, ticker` keys
- **THEN** external alpha generation fails before upload or merge

#### Scenario: Output is missing requested alpha columns
- **WHEN** DolphinDB returns a table missing any requested canonical alpha column
- **THEN** the system rejects the output and reports the missing columns

#### Scenario: Output contains unexpected alpha columns
- **WHEN** DolphinDB returns extra columns matching an Alpha101 or Alpha191 prefix outside the requested canonical set
- **THEN** the system rejects the output and reports the unexpected columns

#### Scenario: Output keys do not align with input panel
- **WHEN** the DolphinDB result contains keys outside the input panel or omits all requested family values for matching keys
- **THEN** the system reports the mismatch and refuses to silently produce an unusable panel

### Requirement: External Alpha Manifest
The system SHALL write a manifest JSON next to the generated parquet describing provenance, field mapping, input/output hashes, and validation results.

#### Scenario: Manifest is written after successful generation
- **WHEN** external alpha generation succeeds
- **THEN** the system writes a manifest containing factor families, generated columns, input file metadata, output file metadata, schema hashes, DolphinDB connection metadata, module version labels, selected input fields, generated time, row count, and validation summary

#### Scenario: Sensitive values are provided
- **WHEN** the user provides credentials or local secrets for DolphinDB
- **THEN** the manifest does not record passwords, `.env` content, TuShare tokens, or other secret values

#### Scenario: Fallback field is used
- **WHEN** field mapping falls back from a preferred field to an alternate field
- **THEN** the manifest records both the preferred field and the actual selected field

### Requirement: Backtest Consumption Boundary
The system SHALL keep DolphinDB out of the normal backtest runtime path.

#### Scenario: Generated panel is used for backtesting
- **WHEN** a generated external alpha parquet is passed to the existing `moneytree` backtest command
- **THEN** the backtest consumes alpha columns as normal numeric features through the existing feature selection and feature lag pipeline

#### Scenario: Backtest runs without DolphinDB installed
- **WHEN** a user runs normal backtests without requesting external alpha generation
- **THEN** the system does not import or require the DolphinDB Python client

### Requirement: DolphinDB WSL Docker Documentation
The project SHALL document the recommended WSL development setup for DolphinDB external factor generation.

#### Scenario: User follows WSL setup documentation
- **WHEN** a WSL user reads the DolphinDB Alpha101/191 documentation
- **THEN** the documentation explains the Docker Desktop WSL 2 backend recommendation, container port, mounted module/data/log directories, required DolphinDB module filenames, and example generation commands

#### Scenario: User reviews factor catalog documentation
- **WHEN** a user reads the factor catalog documentation
- **THEN** it clearly states that the 810-row catalog includes 292 external Alpha101/191 columns and 518 locally generated Alpha158/360 columns
