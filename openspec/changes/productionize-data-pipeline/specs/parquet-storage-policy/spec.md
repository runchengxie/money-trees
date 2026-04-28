## ADDED Requirements

### Requirement: Documented parquet defaults
The project SHALL document that new Money Trees parquet writes default to `zstd` compression with level 3 where supported.

#### Scenario: User checks data status documentation
- **WHEN** the user reads `docs/data_status.md`
- **THEN** the document describes the default parquet compression policy for raw cache, base panel, factor store, and artifacts

### Requirement: Consistent parquet CLI options
Parquet-producing CLIs SHALL expose consistent `--compression`, `--compression-level`, and `--row-group-size` options where the underlying writer supports them.

#### Scenario: User writes DolphinDB alpha output
- **WHEN** the user runs `moneytrees-dolphindb-alphas` with parquet output options
- **THEN** compression, compression level, and row group size are passed to the parquet writer for wide output and factor-store output

#### Scenario: User builds a factor store
- **WHEN** the user runs `moneytrees-factor-store` with parquet output options
- **THEN** compression, compression level, and row group size are applied to base panel and factor family parquet files

### Requirement: Shared parquet option validation
Parquet option validation SHALL remain centralized so unsupported compression and compression-level combinations fail consistently across CLIs.

#### Scenario: Snappy level is provided
- **WHEN** the user requests `--compression snappy --compression-level 3`
- **THEN** the command fails with a clear validation error because Snappy does not accept a compression level

#### Scenario: Invalid row group size is provided
- **WHEN** the user requests `--row-group-size 0`
- **THEN** the command fails with a clear validation error

### Requirement: Parquet metadata in manifests
Writers that produce manifests SHALL record selected parquet compression options in those manifests.

#### Scenario: Factor store manifest is written
- **WHEN** a factor store is generated with explicit parquet options
- **THEN** `manifest.json` records compression, compression level, and row group size where available

#### Scenario: External alpha manifest is written
- **WHEN** external Alpha101 or Alpha191 output is generated with explicit parquet options
- **THEN** the external alpha manifest records compression, compression level, and row group size where available

### Requirement: No implicit storage migration
The parquet storage policy change SHALL NOT require rewriting existing raw cache, base panel, factor store, or artifact parquet files.

#### Scenario: Existing data uses older compression
- **WHEN** existing parquet files were written with a different compression codec
- **THEN** they remain readable and are not rewritten unless the user explicitly runs a rewrite command
