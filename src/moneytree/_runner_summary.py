from __future__ import annotations

from typing import Any

import pandas as pd

from moneytree._runner_holdout import HoldoutResult


def _format_percent(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value * 100:.2f}%"


def _format_float(value: float, precision: int = 6) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:.{precision}f}"


def _metric(metrics: dict[str, float], key: str) -> float:
    return float(metrics.get(key, float("nan")))


def build_run_summary_text(
    *,
    benchmark_name: str,
    strategy_nav: pd.Series,
    strategy_turnover: pd.Series,
    period_ic: pd.Series,
    period_rank_ic: pd.Series,
    segment_a: Any,
    segment_b: Any,
    metrics: dict[str, float],
    tuning_cv_folds: int,
    holdout_result: HoldoutResult | None,
) -> str:
    if strategy_nav.empty:
        date_span = "n/a -> n/a"
    else:
        date_span = (
            f"{pd.Timestamp(strategy_nav.index.min()).strftime('%Y-%m-%d')} -> "
            f"{pd.Timestamp(strategy_nav.index.max()).strftime('%Y-%m-%d')}"
        )
    strategy_total_return = _metric(metrics, "strategy_total_return")
    benchmark_total_return = _metric(metrics, "benchmark_total_return")
    excess_total_return = strategy_total_return - benchmark_total_return
    benchmark_label = benchmark_name or "Benchmark"
    if pd.isna(excess_total_return):
        relative_result = "n/a"
    elif excess_total_return > 0:
        relative_result = f"Outperformed {benchmark_label} by {_format_percent(excess_total_return)}."
    elif excess_total_return < 0:
        relative_result = (
            f"Underperformed {benchmark_label} by {_format_percent(abs(excess_total_return))}."
        )
    else:
        relative_result = f"Matched {benchmark_label} total return."

    lines = [
        "Backtest run summary",
        f"Date span: {date_span}",
        f"NAV points: {len(strategy_nav)}",
        "Evaluation protocol: walk-forward OOS rolling backtest (segment A + segment B).",
        (
            f"Time-series CV tuning: enabled ({tuning_cv_folds} expanding folds)."
            if tuning_cv_folds > 1
            else "Time-series CV tuning: disabled (single validation slice)."
        ),
        "",
        f"Performance vs {benchmark_label}",
        f"- Strategy total return: {_format_percent(strategy_total_return)}",
        f"- {benchmark_label} total return: {_format_percent(benchmark_total_return)}",
        f"- Relative result: {relative_result}",
        f"- Strategy annualized return: {_format_percent(_metric(metrics, 'strategy_annualized_return'))}",
        f"- {benchmark_label} annualized return: {_format_percent(_metric(metrics, 'benchmark_annualized_return'))}",
        f"- Strategy sharpe: {_format_float(_metric(metrics, 'strategy_sharpe'))}",
        f"- Strategy sortino: {_format_float(_metric(metrics, 'strategy_sortino'))}",
        f"- Strategy calmar: {_format_float(_metric(metrics, 'strategy_calmar'))}",
        f"- Information ratio: {_format_float(_metric(metrics, 'information_ratio'))}",
        f"- Max drawdown (strategy): {_format_percent(_metric(metrics, 'strategy_max_drawdown'))}",
        "",
        "Tail / Distribution",
        f"- Strategy VaR 95%: {_format_percent(_metric(metrics, 'strategy_var_95'))}",
        f"- Strategy CVaR 95%: {_format_percent(_metric(metrics, 'strategy_cvar_95'))}",
        "",
        "Turnover / Breadth / IC",
        f"- Avg turnover per period: {_format_float(_metric(metrics, 'avg_turnover_per_period'))}",
        f"- Avg active names: {_format_float(_metric(metrics, 'avg_active_names'), precision=2)}",
        (
            "- IC mean / IR / positive rate: "
            f"{_format_float(_metric(metrics, 'ic_mean'))} / "
            f"{_format_float(_metric(metrics, 'ic_ir'))} / "
            f"{_format_percent(_metric(metrics, 'ic_positive_rate'))}"
        ),
        (
            "- Rank IC mean / IR / positive rate: "
            f"{_format_float(_metric(metrics, 'rank_ic_mean'))} / "
            f"{_format_float(_metric(metrics, 'rank_ic_ir'))} / "
            f"{_format_percent(_metric(metrics, 'rank_ic_positive_rate'))}"
        ),
        f"- Turnover data points: {len(strategy_turnover.dropna())}",
        "",
        "Segment diagnostics",
        (
            "- Segment A: "
            f"features={len(segment_a.feature_columns)}, "
            f"train={segment_a.train_start}->{segment_a.train_end}, "
            f"valid={segment_a.valid_start}->{segment_a.valid_end}, "
            f"model={segment_a.model_id}, "
            f"tuning_best={_format_float(segment_a.tuning_best_value)}, "
            f"validation_profit={_format_float(segment_a.validation_profit)}, "
            f"validation_turnover={_format_float(segment_a.validation_turnover)}, "
            f"active_names={segment_a.validation_active_names}"
        ),
        (
            "- Segment B: "
            f"features={len(segment_b.feature_columns)}, "
            f"train={segment_b.train_start}->{segment_b.train_end}, "
            f"valid={segment_b.valid_start}->{segment_b.valid_end}, "
            f"model={segment_b.model_id}, "
            f"tuning_best={_format_float(segment_b.tuning_best_value)}, "
            f"validation_profit={_format_float(segment_b.validation_profit)}, "
            f"validation_turnover={_format_float(segment_b.validation_turnover)}, "
            f"active_names={segment_b.validation_active_names}"
        ),
        "",
        "Artifacts",
        "- OOS period-level diagnostics are exported to oos_period_diagnostics.csv.",
        "- Signal oracle diagnostics are exported to signal_nav.csv and signal_profit.csv.",
        (
            "- Notebook-style report datasets are exported to notebook_report_navs.csv, "
            "notebook_rolling_beta.csv, and notebook_residual_*.csv."
        ),
        "- Feature score curves are exported when selection history is available.",
    ]
    if holdout_result is not None:
        hm = holdout_result.metrics
        overlap_note = "- Holdout overlap note: n/a (main backtest window is empty)."
        if not strategy_nav.empty:
            main_start = pd.Timestamp(strategy_nav.index.min())
            main_end = pd.Timestamp(strategy_nav.index.max())
            holdout_start_ts = pd.Timestamp(holdout_result.holdout_start)
            holdout_end_ts = pd.Timestamp(holdout_result.holdout_end)
            if holdout_start_ts <= main_end and holdout_end_ts >= main_start:
                overlap_note = "- Holdout overlap note: holdout window overlaps the main backtest window."
            else:
                overlap_note = "- Holdout overlap note: no overlap with main backtest window."
        lines.extend(
            [
                "",
                "Final Holdout OOS",
                f"- Holdout date span: {holdout_result.holdout_start} -> {holdout_result.holdout_end}",
                f"- Holdout model source: {holdout_result.model_segment}",
                (
                    "- Holdout strategy total return: "
                    f"{_format_percent(float(hm.get('strategy_total_return', float('nan'))))}"
                ),
                (
                    f"- Holdout {holdout_result.benchmark_name or 'Benchmark'} total return: "
                    f"{_format_percent(float(hm.get('benchmark_total_return', float('nan'))))}"
                ),
                overlap_note,
                "- Holdout artifacts are exported to holdout/*.csv and holdout/metrics.json.",
            ]
        )
    return "\n".join(lines)
