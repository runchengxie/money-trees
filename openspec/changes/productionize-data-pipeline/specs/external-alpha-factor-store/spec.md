## ADDED Requirements

### Requirement: External alpha factor-store output
The DolphinDB alpha CLI SHALL support writing validated Alpha101 and Alpha191 factor families directly into a Money Trees factor store through `--factor-store-output`.

#### Scenario: Alpha101 and Alpha191 are written to factor store
- **WHEN** the user runs `moneytrees-dolphindb-alphas --input <panel> --factor-store-output <store> --alpha101 --alpha191`
- **THEN** the factor-store manifest includes `alpha101` and `alpha191` families with expected prefixes, rows, columns, partition metadata, factor dtype, compression metadata, and external generation metadata

#### Scenario: Existing wide output remains available
- **WHEN** the user runs the existing `moneytrees-dolphindb-alphas --input <panel> --output <wide-panel> --alpha101`
- **THEN** the command still writes a merged wide panel and external alpha manifest with compatible behavior

### Requirement: Output path compatibility
The DolphinDB alpha CLI SHALL require at least one output target, either `--output` for a wide panel, `--factor-store-output` for a factor store, or both.

#### Scenario: No output target is provided
- **WHEN** the user runs `moneytrees-dolphindb-alphas --input <panel> --alpha101` without `--output` or `--factor-store-output`
- **THEN** argument validation fails with a clear message

#### Scenario: Factor-store-only mode is requested
- **WHEN** the user runs with `--factor-store-output <store> --no-wide-output`
- **THEN** the command writes factor-store files and does not require or create a wide panel output

### Requirement: External alpha validation
The factor-store output path SHALL enforce the same Alpha101 and Alpha191 validation contract as the wide-panel merge path.

#### Scenario: Alpha101 output is missing a column
- **WHEN** DolphinDB returns an Alpha101 table missing one of `alpha101_001` through `alpha101_101`
- **THEN** the command fails before writing a final factor-store manifest

#### Scenario: External output has unknown keys
- **WHEN** DolphinDB returns `date, ticker` keys outside the input panel
- **THEN** the command fails before writing a final factor-store manifest

#### Scenario: External output has no usable values
- **WHEN** DolphinDB returns expected columns but all matched factor values are null
- **THEN** the command fails before writing a final factor-store manifest

### Requirement: Partitioned external family storage
The factor-store output path SHALL write external factor families as partitioned family files using date chunks after full-range DolphinDB calculation and validation.

#### Scenario: Chunk size is specified
- **WHEN** the user passes `--chunk-trade-dates 60`
- **THEN** each external family is written under `factors/<family>/part-*.parquet` with at most 60 target trade dates per partition, except the final shorter partition

#### Scenario: Full-range calculation is used
- **WHEN** the command generates Alpha101 or Alpha191 for factor-store output
- **THEN** DolphinDB receives the full input panel for the requested date range before Python partitions the validated result for storage

### Requirement: External factor-store manifest metadata
The factor-store manifest SHALL record enough metadata to audit external Alpha101 and Alpha191 production without serializing secrets.

#### Scenario: Manifest is written
- **WHEN** external factors are written to a factor store
- **THEN** the manifest records requested families, generated families, field mapping, validation summary, DolphinDB host and port, DolphinDB server version when available, DolphinDB Python client version when available, module versions, factor dtype, compression, and chunk trade dates

#### Scenario: Secret inputs are present
- **WHEN** the DolphinDB password or other secret-like values are available during generation
- **THEN** the factor-store manifest does not include those secret values

### Requirement: Incremental factor-store compatibility
The external alpha writer SHALL work with an existing factor store when the existing base panel index matches the input panel.

#### Scenario: Existing store has local families
- **WHEN** a factor store already contains Alpha158 or Alpha360 for the same base panel and the user writes Alpha101
- **THEN** the existing local families remain in the manifest and Alpha101 is added without rewriting unrelated factor families

#### Scenario: Existing store base panel differs
- **WHEN** the existing factor-store base panel index differs from the input panel
- **THEN** the command fails with a clear alignment error before writing external factor partitions
