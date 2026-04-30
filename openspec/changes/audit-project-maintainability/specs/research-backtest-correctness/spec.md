## ADDED Requirements

### Requirement: Preprocessing Does Not Fill Targets Or State Columns
The data preprocessing pipeline SHALL avoid ticker-level forward fill for target, label, benchmark, tradability, suspension, ST, limit-up, limit-down, and prediction output columns.

#### Scenario: Missing next period return exists
- **WHEN** a ticker has a missing `next_period_return` on a date
- **THEN** `preprocess_data()` SHALL leave that missing return unavailable for label construction instead of copying a previous future return

#### Scenario: Missing tradability state exists
- **WHEN** `is_suspended`, `is_st`, `hit_up_limit`, `hit_down_limit`, `is_tradable`, or `tradeable` contains a missing value
- **THEN** preprocessing SHALL not forward fill that state unless a market profile explicitly provides a point-in-time safe fill rule

#### Scenario: Feature column has a gap
- **WHEN** a feature-like numeric column has a ticker-level gap
- **THEN** preprocessing MAY forward fill that feature according to existing missing-value settings

### Requirement: Benchmark NAV Mode Is Explicit
Benchmark NAV construction SHALL use an explicit mode for the configured benchmark cumulative column.

#### Scenario: Benchmark cumulative column is NAV or index level
- **WHEN** `benchmark_cum_mode` is `nav`
- **THEN** `build_benchmark_nav()` SHALL compute the normalized benchmark series as `benchmark / first_valid_benchmark`

#### Scenario: Benchmark cumulative column is cumulative return
- **WHEN** `benchmark_cum_mode` is `cumulative_return`
- **THEN** `build_benchmark_nav()` SHALL compute the normalized benchmark series as `1 + benchmark - first_valid_benchmark`

#### Scenario: Benchmark mode is invalid
- **WHEN** the configured benchmark mode is not supported
- **THEN** configuration validation SHALL fail with a clear error that names the invalid value

### Requirement: Performance Metrics Include The Full Return Interval
Performance metrics SHALL calculate total and annualized returns from period return series when those series are available.

#### Scenario: Strategy returns are provided
- **WHEN** `compute_performance_metrics()` receives `strategy_returns`
- **THEN** `strategy_total_return` SHALL equal `(1 + strategy_returns).prod() - 1` after alignment and missing-value removal

#### Scenario: Benchmark returns are provided
- **WHEN** `compute_performance_metrics()` receives `benchmark_returns`
- **THEN** `benchmark_total_return` SHALL equal `(1 + benchmark_returns).prod() - 1` after alignment and missing-value removal

#### Scenario: Return series are absent
- **WHEN** period return series are not provided
- **THEN** metrics MAY fall back to NAV start/end ratios for backward compatibility

### Requirement: Missing Feature Policy Is Configurable And Safe By Default
Rolling backtest and holdout paths SHALL handle missing selected feature columns through an explicit policy.

#### Scenario: Missing feature appears under default policy
- **WHEN** a selected feature column is absent from the train, test, or holdout frame and `missing_feature_policy` is `error`
- **THEN** the run SHALL fail with a clear message that lists the missing feature names and frame role

#### Scenario: Legacy compatibility fills missing feature
- **WHEN** `missing_feature_policy` is `warn_fill_zero` or `fill_zero`
- **THEN** the run SHALL fill missing feature columns with `0.0`; `warn_fill_zero` SHALL emit a warning or record the fallback in run output

#### Scenario: Factor store family is not loaded
- **WHEN** selected features require a factor family that is absent from the loaded input
- **THEN** the default policy SHALL fail before model training begins

### Requirement: TuShare Latest ST Flag Is Not Presented As Historical ST State
The TuShare data source SHALL make the point-in-time limitations of ST status derived from `stock_basic.name` explicit.

#### Scenario: ST flag is derived from stock_basic name
- **WHEN** `_merge_stock_basic()` creates `is_st` from the latest or list-status stock basic name
- **THEN** the output metadata, warning, or column naming SHALL indicate that the flag is not a verified historical point-in-time ST series

#### Scenario: Historical ST source is configured
- **WHEN** a future historical ST source is configured
- **THEN** the market profile MAY treat the resulting field as eligible for strict tradability filtering without the latest-name warning

### Requirement: Exposure Diagnostics Are Recorded
Portfolio and backtest outputs SHALL expose realized gross, net, and unallocated exposure when portfolio constraints prevent target exposure from being fully allocated.

#### Scenario: Cap prevents full exposure
- **WHEN** `max_name_weight`, `min_names_per_side`, or the available tradable universe prevents target gross exposure from being reached
- **THEN** output diagnostics SHALL record target gross, realized gross, target net, realized net, and unallocated exposure for the affected period

#### Scenario: QP fallback occurs
- **WHEN** `signal_risk_qp` cannot solve and falls back to heuristic weights
- **THEN** the period diagnostics SHALL record that fallback so users can distinguish optimizer failure from model behavior

### Requirement: Validation And Tuning Periods Are Auditable
The backtest runner SHALL record validation periods and tuning inputs used to select features or model parameters.

#### Scenario: Segment fit completes
- **WHEN** segment A or segment B feature selection or tuning is run
- **THEN** run output SHALL include the train and validation date ranges, selected feature count, model id, and tuning status for that segment

#### Scenario: Holdout is configured
- **WHEN** holdout is enabled
- **THEN** holdout output SHALL identify the segment model used and SHALL keep holdout dates separate from tuning and validation date ranges
