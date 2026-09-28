# Alpha 810 Evidence Export and Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned, auditable public Alpha 810 evidence snapshot and publish the project documentation with MkDocs through GitHub Actions without changing the existing backtest CLI.

**Architecture:** `money-trees` will expose a pure-Python publication module that consumes an already prepared panel and the existing factor IC evaluator, emits only aggregate factor evidence plus reproducibility metadata, and rejects fields outside the public contract. A CLI will wrap this module for local/hardware-box generation; GitHub Actions will build only checked-in documentation and never access local research data.

**Tech Stack:** Python 3.10+, pandas, PyYAML, pytest, MkDocs Material, GitHub Pages Actions.

**Spec:** `docs/superpowers/specs/2026-09-28-alpha-research-boundary-design.md`

## Global Constraints

- Preserve existing `moneytree` import names and all current backtest CLI aliases.
- Do not commit raw panels, factor values by ticker, portfolio weights, credentials, or local absolute paths.
- Public snapshots contain aggregate statistics and sampled aggregate series only; no individual security identity is required.
- Every snapshot records schema version, generated time, sample range, data version label, code revision when available, and calculation configuration.
- MkDocs and GitHub Actions document and publish the public contract; they do not run research calculations.
- Formal portfolio construction, risk, execution, and task runtime remain outside this plan.

## Review Focus

- A panel missing `date`, `ticker`, or the configured forward-return column must fail with a targeted validation error; test in the publication API task.
- A factor with no valid observations must remain in the catalog with null metrics rather than being silently omitted; test in the summary task.
- NaN and infinite aggregate metrics must serialize as JSON `null`, never non-standard JSON tokens; test in the snapshot writer task.
- Public output must not contain ticker-level rows, absolute input paths, or arbitrary input columns; test in the redaction task.
- Running the CLI against a dirty or non-Git directory must still produce a valid snapshot with nullable revision metadata; test in the CLI task.

### Task 1: Define the public evidence schema and pure publication API

**Files:**
- Create: `src/moneytree/factors/publication.py`
- Create: `tests/test_factor_publication.py`
- Modify: `src/moneytree/factors/__init__.py`

**Interfaces:**
- Consumes: a `date,ticker` panel, selected factor names, forward-return column, data-version label, and optional repository metadata.
- Produces: `PUBLIC_SNAPSHOT_SCHEMA_VERSION = "1.0"`; `build_factor_evidence_snapshot(panel, factors, *, return_column="next_period_return", data_version="unknown", config=None, git_metadata=None) -> dict[str, object]`.
- Output shape: top-level `kind="moneytree_factor_evidence_snapshot"`, `schema_version`, `generated_at`, `data_version`, `code_revision`, `dataset`, `factors`, and `public_limits`; each factor includes `name`, `family`, `coverage`, `ic`, `rank_ic`, and `group_returns` aggregate fields.

- [ ] **Step 1: Write failing contract tests** for required panel columns, factor retention, schema keys, null serialization values, and no ticker-level output.
- [ ] **Step 2: Run `uv run pytest -q tests/test_factor_publication.py`** and verify the new API tests fail.
- [ ] **Step 3: Implement the pure builder** by reusing `compute_factor_ic` and `summarize_factor_ic`; derive dataset date range/trading-day/observation counts and grouped return aggregates without importing CLI or filesystem code.
- [ ] **Step 4: Add explicit redaction** so only allowlisted aggregate fields enter the public payload; normalize non-finite floats to `None`.
- [ ] **Step 5: Run the focused tests** and verify all contract tests pass.
- [ ] **Step 6: Commit** with `feat: add public Alpha evidence snapshot contract`.

### Task 2: Add the local snapshot CLI and fixture-based release audit

**Files:**
- Create: `src/moneytree/cli/factor_evidence.py`
- Create: `tests/test_factor_evidence_cli.py`
- Modify: `pyproject.toml`
- Modify: `src/moneytree/cli/__init__.py`

**Interfaces:**
- Consumes: `--panel`, `--factors`, `--return-column`, `--data-version`, `--output`, optional `--config`, and `--format`.
- Produces: one UTF-8 JSON snapshot at the requested output path and a concise stdout summary; `moneytrees-factor-evidence` and compatible `moneytree-factor-evidence` entry points.

- [ ] **Step 1: Write failing CLI tests** using a temporary synthetic panel; assert output path, top-level kind, selected factors, and non-zero exit for missing inputs.
- [ ] **Step 2: Run the focused CLI tests** and verify they fail before the entry point exists.
- [ ] **Step 3: Implement argument parsing and file IO** in the CLI, keeping calculation in `factors/publication.py`; resolve factor names from a comma-separated list or a text file.
- [ ] **Step 4: Add a public-release audit helper** that rejects forbidden keys/values, absolute paths, ticker-level records, and non-finite JSON values.
- [ ] **Step 5: Run `uv run pytest -q tests/test_factor_evidence_cli.py tests/test_factor_publication.py`** and verify all pass.
- [ ] **Step 6: Run `uv run ruff check .`** and commit with `feat: add Alpha evidence export CLI`.

### Task 3: Add MkDocs documentation and GitHub Pages workflow

**Files:**
- Create: `mkdocs.yml`
- Create: `.github/workflows/deploy-docs.yml`
- Create: `docs/public-factor-evidence.md`
- Create: `docs/publication-audit.md`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `pyproject.toml` or a new `requirements-docs.txt` with pinned documentation dependencies

**Interfaces:**
- Consumes: checked-in Markdown documentation only.
- Produces: a MkDocs site with pages for project boundary, evidence schema, local generation, release audit, and limitations; a GitHub Pages deployment artifact from `main` and manual dispatch.

- [ ] **Step 1: Add documentation tests** that verify the MkDocs navigation references existing files and that README links to the public evidence guide.
- [ ] **Step 2: Run the documentation tests** and verify the new references fail before configuration exists.
- [ ] **Step 3: Implement `mkdocs.yml`** with a stable site name, repository URL, navigation, Material theme, and no source-data plugin.
- [ ] **Step 4: Write the evidence and audit guides** with the exact JSON contract, local hard-drive workflow, forbidden public fields, and separation from `quant-platform` and `quant-backtest-runtime`.
- [ ] **Step 5: Implement `deploy-docs.yml`** using pinned major action versions, Python setup, dependency installation, `mkdocs build --strict`, Pages artifact upload, and deployment.
- [ ] **Step 6: Run `mkdocs build --strict` and the documentation tests**; commit with `docs: publish Alpha evidence contract with MkDocs`.

### Task 4: End-to-end synthetic release fixture

**Files:**
- Create: `scripts/build_public_factor_snapshot.py`
- Create: `tests/test_public_factor_release.py`
- Create: `tests/fixtures/public_factor_panel.parquet` only if repository fixture policy permits; otherwise generate it inside the test.
- Modify: `docs/publication-audit.md`

**Interfaces:**
- Consumes: a synthetic or explicitly supplied private panel path and selected factors.
- Produces: a public snapshot suitable for copying into `quant-factor-observatory/site/public/data/alpha810-snapshot.json`; never copies the input panel.

- [ ] **Step 1: Write a release test** that generates synthetic data in `tmp_path`, runs the script, audits the JSON, and asserts the output contains aggregate metrics only.
- [ ] **Step 2: Run the release test** and verify it fails before the script exists.
- [ ] **Step 3: Implement the script** as a thin composition of the CLI/publication API with explicit output-directory safety checks.
- [ ] **Step 4: Run the release test, full Python tests, and Ruff**.
- [ ] **Step 5: Commit** with `test: verify synthetic Alpha public release`.

## Cross-repository handoff

After this plan is merged, `quant-factor-observatory` should add an independent consumer plan for `alpha810-snapshot.json`. The provider PR must merge first; the consumer must pin or document the accepted `schema_version` and use synthetic checked-in data for frontend tests. No frontend PR should depend on a development worktree or local hard-drive path.

