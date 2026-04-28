## ADDED Requirements

### Requirement: Python runner Dockerfile
The repository SHALL provide a Dockerfile for a Money Trees Python runner image that can install selectable optional dependency groups without bundling runtime data or secrets.

#### Scenario: Research image is built
- **WHEN** the user builds the image with a research extra argument
- **THEN** the image installs Money Trees with the research optional dependencies and exposes the Money Trees CLIs

#### Scenario: External-alpha image is built
- **WHEN** the user builds the image with an external-alpha extra argument
- **THEN** the image includes the DolphinDB Python client dependency but does not install or run a DolphinDB server

### Requirement: Docker ignore rules
The repository SHALL provide `.dockerignore` rules that exclude runtime outputs and local secrets from image build context.

#### Scenario: Docker context is prepared
- **WHEN** Docker builds the Money Trees image
- **THEN** `.env`, data directories, artifact directories, cache directories, raw parquet outputs, generated manifests, and other local runtime outputs are excluded from the build context

### Requirement: Separate DolphinDB compose service
The repository SHALL provide a compose file for external Alpha101/191 production where DolphinDB runs as a separate service from the Money Trees Python runner.

#### Scenario: Compose stack is started
- **WHEN** the user starts the alpha compose stack
- **THEN** one service runs the Money Trees Python runner and a separate service runs DolphinDB with its own port, volume mounts, and module paths

#### Scenario: Money Trees connects to DolphinDB
- **WHEN** `moneytrees-dolphindb-alphas` is run inside the Money Trees service
- **THEN** the command can target the DolphinDB service by compose service name and configured port

### Requirement: Runtime volume layout
The compose runtime SHALL mount data, artifacts, configs, and DolphinDB modules as volumes instead of baking them into container images.

#### Scenario: Data is produced in compose
- **WHEN** a containerized command writes panel, cache, factor-store, or artifact outputs
- **THEN** those outputs appear under host-mounted runtime directories such as `data/` or `artifacts/`

### Requirement: Secret handling in containers
The container runtime MUST NOT require committing `.env`, TuShare tokens, DolphinDB passwords, or license material to the repository.

#### Scenario: Environment variables are provided
- **WHEN** the user supplies credentials through host environment variables or local ignored files
- **THEN** compose passes them to the relevant service without adding those values to tracked project files

### Requirement: Documentation for containerized workflow
The project documentation SHALL show the intended container flow for TuShare data, local factor-store generation, DolphinDB external alpha generation, and backtesting.

#### Scenario: User reads the docs
- **WHEN** a user opens the container or runbook documentation
- **THEN** they can identify which commands run in the Python runner, which service provides DolphinDB, which directories are mounted, and which files must not be committed
