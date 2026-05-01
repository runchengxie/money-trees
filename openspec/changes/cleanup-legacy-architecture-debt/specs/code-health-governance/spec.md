## ADDED Requirements

### Requirement: Maintainability Audit Is Recorded
The project SHALL maintain a code health audit that identifies oversized modules, mixed responsibilities, legacy compatibility surfaces, and quality-gate gaps before implementation removes or rewrites those areas.

#### Scenario: Audit identifies high-risk modules
- **WHEN** maintainers review code health work for this change
- **THEN** the audit lists the largest core Python modules, their dominant responsibilities, and the recommended refactor direction

#### Scenario: Audit distinguishes evidence from preference
- **WHEN** a module is proposed for splitting or cleanup
- **THEN** the audit cites local evidence such as line count, maintenance documentation, tests, imports, or documented CLI behavior

### Requirement: Compatibility Surfaces Have Lifecycle States
The project SHALL classify historical scripts, transitional presets, pickle migration paths, legacy notebook behavior, and CLI aliases with explicit lifecycle states and replacement guidance.

#### Scenario: Deprecated entry point remains available during transition
- **WHEN** an entry point is classified as deprecated
- **THEN** the entry point still works or fails with a clear migration message until a later removal change is approved

#### Scenario: Compatibility item has a replacement
- **WHEN** a script, preset, or alias is marked deprecated or removal-candidate
- **THEN** documentation names the preferred replacement command, config, or API

### Requirement: Core Refactors Preserve Public Facades
Internal refactors of central modules SHALL preserve existing public import paths and console script behavior unless a separate proposal marks a breaking change.

#### Scenario: Factor store internals are split
- **WHEN** factor-store implementation moves into smaller modules
- **THEN** imports from `moneytree.factor_store` continue to expose the documented writer, loader, validation, and memory-estimation functions

#### Scenario: Runner internals are split
- **WHEN** backtest orchestration helpers move into smaller modules
- **THEN** existing callers can still use the current `moneytree.runner` facade and CLI behavior

### Requirement: Data Contracts Remain Protected
Maintenance refactors SHALL preserve the canonical `date, ticker` panel shape, factor-store manifest compatibility, optional dependency behavior, and documented default research path.

#### Scenario: Refactor touches data or factor-store code
- **WHEN** implementation changes data loading, factor-store writing, factor-store loading, or external alpha integration
- **THEN** targeted tests cover key alignment, selected factor families, manifest validation, and clear optional dependency errors

#### Scenario: Legacy pickle path is changed
- **WHEN** implementation changes pickle migration or pickle input support
- **THEN** tests and docs state that pickle is only for trusted legacy migration and parquet remains the preferred format

### Requirement: Quality Gates Are Staged
The project SHALL stage stricter code quality rules so they improve maintainability without mixing broad mechanical churn with behavioral refactors.

#### Scenario: New lint rules are evaluated
- **WHEN** complexity, simplification, return, or unused-argument rules are proposed
- **THEN** the implementation records whether each rule is enforced immediately, scoped to touched modules, or tracked as backlog

#### Scenario: Long lines are addressed in touched modules
- **WHEN** a refactor edits a module with long lines or dense formatting
- **THEN** touched code follows the configured line-length intent unless preserving readability or generated content requires otherwise

### Requirement: Ambiguous Utility Modules Are Resolved
The project SHALL resolve utility modules whose public or internal status is unclear before deleting or expanding them.

#### Scenario: Factor operator utilities are reviewed
- **WHEN** `moneytree.factors.ops` is audited
- **THEN** maintainers either document it as internal with focused tests or promote selected stable operators through the package API

#### Scenario: Unused utility is removed
- **WHEN** a utility function has no internal tests, public documentation, or runtime references
- **THEN** it can be removed only with a targeted test or audit note showing the absence of supported usage
