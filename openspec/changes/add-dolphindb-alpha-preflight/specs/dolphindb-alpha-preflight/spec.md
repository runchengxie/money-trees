## ADDED Requirements

### Requirement: Preflight validates required DolphinDB modules

The system SHALL validate the DolphinDB server modules required by the selected external alpha families before running Alpha101/191 generation.

#### Scenario: Alpha101 module preflight passes

- **WHEN** the user runs `moneytrees-dolphindb-alphas` with `--alpha101`
- **THEN** the CLI validates that DolphinDB can load `wq101alpha`, `prepare101`, and `moneytreeAlpha` before invoking `calcMoneyTreeAlpha101`

#### Scenario: Alpha191 module preflight passes

- **WHEN** the user runs `moneytrees-dolphindb-alphas` with `--alpha191`
- **THEN** the CLI validates that DolphinDB can load `gtja191Alpha`, `gtja191Prepare`, and `moneytreeAlpha` before invoking `calcMoneyTreeAlpha191`

#### Scenario: Combined module preflight passes

- **WHEN** the user runs `moneytrees-dolphindb-alphas` with both `--alpha101` and `--alpha191`
- **THEN** the CLI validates the required Alpha101 modules, Alpha191 modules, and `moneytreeAlpha` wrapper module before invoking either wrapper function

### Requirement: Preflight reports actionable missing module diagnostics

The system SHALL convert module preflight failures into a Money Trees error message that names the failing DolphinDB module and tells the user where local `.dos` modules are expected.

#### Scenario: Missing prepare101 module

- **WHEN** DolphinDB fails to load `prepare101` during Alpha101 preflight
- **THEN** the CLI error names `prepare101`, mentions `prepare101.dos`, and points to `docker/dolphindb/modules/` as the local module directory used by the repository Docker setup

#### Scenario: Module version arguments are misunderstood

- **WHEN** module preflight fails after the user provided `--wq101-module-version`, `--gtja191-module-version`, or `--moneytree-alpha-module-version`
- **THEN** the CLI error explains that those arguments record manifest metadata and do not change DolphinDB `use` module names

### Requirement: Preflight validates requested wrapper functions

The system SHALL validate that the `moneytreeAlpha` module exposes the wrapper function required for each selected family before generation starts.

#### Scenario: Alpha101 wrapper function is missing

- **WHEN** the user requests Alpha101 and `moneytreeAlpha` does not expose the configured Alpha101 wrapper function
- **THEN** the CLI fails before generation with an error naming the configured function, defaulting to `calcMoneyTreeAlpha101`

#### Scenario: Alpha191 wrapper function is missing

- **WHEN** the user requests Alpha191 and `moneytreeAlpha` does not expose the configured Alpha191 wrapper function
- **THEN** the CLI fails before generation with an error naming the configured function, defaulting to `calcMoneyTreeAlpha191`

#### Scenario: Custom wrapper function names are respected

- **WHEN** the user passes `--alpha101-function` or `--alpha191-function`
- **THEN** preflight validates the configured function names rather than only the default names

### Requirement: Documentation describes staged DolphinDB Alpha101/191 recovery

The system SHALL document the staged recovery flow for incomplete DolphinDB Alpha101/191 environments.

#### Scenario: User follows setup documentation

- **WHEN** the user reads the DolphinDB Alpha101/191 documentation after a missing-module failure
- **THEN** the documentation lists the required `.dos` files, explains the Docker module mount path, provides a standalone module-loading verification command, and recommends running Alpha101 alone, Alpha191 alone, and then both together into factor store

#### Scenario: External module boundary is documented

- **WHEN** the user reads the DolphinDB Alpha101/191 documentation
- **THEN** the documentation states that third-party DolphinDB formula modules and production local wrapper `.dos` files are not committed to the repository
