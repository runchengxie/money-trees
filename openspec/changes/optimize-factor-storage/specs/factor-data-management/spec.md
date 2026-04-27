## ADDED Requirements

### Requirement: Configurable Factor Dtype
The system SHALL provide a configurable dtype policy for alpha factor columns produced or merged by Money Trees, defaulting to `float32` for persisted factor columns and allowing `float64` for precision-sensitive runs.

#### Scenario: Local factors default to float32
- **WHEN** a user generates Alpha158 or Alpha360 columns through the TuShare CLI without overriding the factor dtype
- **THEN** persisted columns whose names start with `alpha158_` or `alpha360_` are stored as `float32`

#### Scenario: External factors default to float32
- **WHEN** a user generates Alpha101 or Alpha191 columns through the DolphinDB external-alpha CLI without overriding the factor dtype
- **THEN** persisted columns whose names start with `alpha101_` or `alpha191_` are stored as `float32`

#### Scenario: User keeps float64 factors
- **WHEN** a user passes the supported dtype option with `float64`
- **THEN** generated or merged alpha factor columns are persisted as `float64`

#### Scenario: Non-factor columns are not globally downcast
- **WHEN** factor dtype coercion is applied to a panel
- **THEN** columns outside the Alpha101, Alpha191, Alpha158, and Alpha360 factor prefixes retain their existing dtype unless another existing code path changes them

### Requirement: Wide Panel Compatibility
The system SHALL keep existing single-file wide-panel parquet workflows functional while adding storage optimizations.

#### Scenario: TuShare wide-panel output remains available
- **WHEN** a user runs the TuShare CLI with local factor families and a single `--output` path
- **THEN** the command writes a parquet panel containing the canonical `date, ticker` index and requested local factor columns in the same file

#### Scenario: DolphinDB merged output remains available
- **WHEN** a user runs the DolphinDB external-alpha CLI with a single `--output` path
- **THEN** the command writes a merged parquet panel and a factor manifest using the existing external-alpha validation rules

#### Scenario: Existing backtest inputs remain valid
- **WHEN** a user passes an existing wide-panel parquet or pickle file to the backtest CLI
- **THEN** the backtest data path can load and preprocess that file without requiring a factor-store manifest

### Requirement: Factor Selection and Column Pruning
The system SHALL allow users to select factor families or prefixes for a run and SHALL avoid loading unselected parquet columns when the input format supports column pruning.

#### Scenario: Include only Alpha158 features
- **WHEN** a user configures a backtest to include only the `alpha158_` factor prefix
- **THEN** Alpha360, Alpha101, and Alpha191 columns are excluded from the model feature set

#### Scenario: Parquet input is column-pruned
- **WHEN** a parquet input contains unselected factor columns and the requested columns can be resolved from the parquet schema
- **THEN** the loader calls parquet column selection so unselected factor columns are not read into memory

#### Scenario: Required non-factor columns are preserved
- **WHEN** factor prefix selection is enabled
- **THEN** required date, ticker, return, benchmark, label, tradability, and configured extra-drop columns needed for preprocessing and reporting are still loaded or preserved

#### Scenario: Missing requested prefix is reported clearly
- **WHEN** a user requests a factor prefix or family that is not present in the input data
- **THEN** the system reports the missing prefix or family with a clear error or warning before model training proceeds

### Requirement: Documented Storage Guidance
The system SHALL document expected storage scale, recommended artifact boundaries, and lightweight execution patterns for full-market factor research.

#### Scenario: Runbook explains storage pressure
- **WHEN** a user reads the runbook
- **THEN** it describes why full 810-factor, full-market, multi-year panels can reach tens of GB and why repeated wide-panel outputs can multiply storage usage

#### Scenario: Cookbook includes lightweight examples
- **WHEN** a user reads the cookbook
- **THEN** it includes examples for using raw cache, running a subset of local factors, and avoiding unnecessary full alpha-all panel generation during debugging

#### Scenario: Documentation distinguishes durable and experiment data
- **WHEN** a user reads the storage guidance
- **THEN** it distinguishes raw cache, base panel, factor store, and experiment artifacts, and states that cleanup must not delete data by default

### Requirement: Additive Factor Store Roadmap
The system SHALL define an additive factor-store path that can separate base panel data from factor-family parquet files while preserving the canonical `date, ticker` key.

#### Scenario: Factor family file uses canonical key
- **WHEN** a factor-family parquet file is written by the factor-store path
- **THEN** it contains or indexes rows by `date, ticker` and stores only that family plus any required key columns

#### Scenario: Dataset manifest describes split inputs
- **WHEN** a split factor dataset is created
- **THEN** a manifest records the base panel path, factor family paths, row counts, column counts, dtype policy, and generation metadata needed to reproduce the joined dataset

#### Scenario: Manifest loading joins requested families
- **WHEN** a backtest or diagnostic command loads a factor-store manifest with selected factor families
- **THEN** it joins only the requested family files onto the base panel and validates `date, ticker` alignment before modeling

#### Scenario: Wide-panel path remains independent
- **WHEN** the factor-store path is not requested
- **THEN** existing wide-panel generation and loading behavior remains available

### Requirement: Inspection Before Cleanup
The system SHALL provide or document storage inspection before any cleanup workflow and SHALL keep cleanup dry-run by default.

#### Scenario: Storage inspection reports major directories
- **WHEN** a user runs or follows the storage inspection workflow
- **THEN** it reports disk usage for raw cache, base panels, factor-family data, and experiment artifacts separately when those paths exist

#### Scenario: Cleanup defaults to dry-run
- **WHEN** a future cleanup command is introduced
- **THEN** it shows the files or directories it would remove without deleting them unless the user explicitly disables dry-run mode
