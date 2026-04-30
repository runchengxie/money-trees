## ADDED Requirements

### Requirement: Project Entry Documents Reflect Current Capabilities
The project SHALL keep README.md, AGENTS.md, and the primary docs index aligned with the current CLI, runtime paths, optional dependencies, data safety rules, and tested capabilities.

#### Scenario: New CLI appears in project scripts
- **WHEN** a console script is defined in `pyproject.toml`
- **THEN** README.md or a file under docs SHALL mention that command or intentionally document why it is hidden from normal users

#### Scenario: Agent instructions list important paths
- **WHEN** a CLI module under `src/moneytree/cli/` becomes part of the supported workflow
- **THEN** AGENTS.md SHALL list the module path or a grouped path entry that covers it

#### Scenario: Data safety rule covers runtime outputs
- **WHEN** documentation describes cleanup, cache, snapshots, factor store, or artifacts
- **THEN** it SHALL state that `data/`, `artifacts/`, raw TuShare cache, factor store files, and `manifest.sqlite` are runtime outputs that must not be deleted without explicit user approval

### Requirement: Testing Documentation Covers The Test Suite
The project SHALL maintain docs/testing.md as a complete inventory of `tests/test_*.py` files and the focused commands needed to run major test groups.

#### Scenario: Test file is added
- **WHEN** a new `tests/test_*.py` file exists
- **THEN** docs/testing.md SHALL include that filename with a short coverage description

#### Scenario: Engineering CLI tests exist
- **WHEN** tests cover data status, data snapshot, factor store, parquet rewrite, container runtime, or project identity behavior
- **THEN** docs/testing.md SHALL include a focused command or table entry for those tests

### Requirement: Documentation Links Stay Valid
The project SHALL verify Markdown links inside README.md and docs point to existing local files or documented external resources.

#### Scenario: Internal Markdown link is edited
- **WHEN** README.md or docs contains a relative Markdown link
- **THEN** the test suite SHALL fail if the target file does not exist

### Requirement: User-Facing Chinese Documentation Uses Stable Terms
The project SHALL use a stable Chinese terminology set for user-facing docs while preserving code identifiers, CLI names, config keys, and file names in English.

#### Scenario: Market profile is mentioned
- **WHEN** user-facing Chinese docs mention a market profile
- **THEN** they SHALL use `市场配置档` on first mention, with `market profile` in parentheses when helpful

#### Scenario: Core data concepts are mentioned
- **WHEN** docs mention panel, factor store, raw cache, manifest, artifacts, holdout, smoke test, registry, benchmark, or tradability filters
- **THEN** they SHALL use the project terminology from AGENTS.md consistently within the same document

#### Scenario: Avoidable indirect contrast pattern is introduced
- **WHEN** docs add an avoidable indirect contrast sentence
- **THEN** the style check SHALL flag it unless the sentence documents a precise contrast that cannot be expressed directly

### Requirement: Historical Compatibility Paths Are Explicit
The project SHALL document compatibility wrappers, legacy presets, pickle migration, and CLI aliases as compatibility paths with clear preferred replacements.

#### Scenario: Compatibility wrapper is documented
- **WHEN** `scripts/build_dolphindb_alphas.py` or another wrapper remains in the repository
- **THEN** docs SHALL identify the preferred console script replacement

#### Scenario: Pickle input is documented
- **WHEN** docs mention pickle input or pickle migration
- **THEN** they SHALL state that pickle files must come from trusted sources and recommend parquet for normal use

#### Scenario: Duplicate preset exists
- **WHEN** `configs/preset/notebook_compat.yaml` duplicates `legacy_notebook_compat.yaml`
- **THEN** docs SHALL mark the duplicate as transitional and direct new users to the legacy reproduction preset only when reproducing older notebook behavior

### Requirement: Maintenance Backlog Tracks Large Responsibility Modules
The project SHALL keep docs/maintenance.md current for modules whose size or responsibility mix increases future change risk.

#### Scenario: Large factor store module exists
- **WHEN** `src/moneytree/factor_store.py` remains the central implementation for local/external factor stores, manifest, partitioning, validation, compression, and loading
- **THEN** docs/maintenance.md SHALL list it as a split candidate with a proposed target structure

#### Scenario: Facade split is planned
- **WHEN** a large module is scheduled for refactor
- **THEN** docs/maintenance.md SHALL state the facade or compatibility import that must be preserved during migration

### Requirement: Quality Gates Improve In Small Batches
The project SHALL expand lint and formatting checks incrementally so mechanical cleanup remains reviewable.

#### Scenario: Ruff rules are expanded
- **WHEN** new Ruff rule groups are enabled
- **THEN** the change SHALL run `uv run ruff check .` and update only the files required by those rules

#### Scenario: Large refactor is proposed
- **WHEN** a change plans to split `runner.py`, `factor_store.py`, `backtest.py`, `portfolio.py`, or `data_sources/tushare.py`
- **THEN** it SHALL include focused tests or golden outputs that protect the public behavior before moving code
