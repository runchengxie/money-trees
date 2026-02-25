#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from strategy.backtest import (  # noqa: E402
    build_rolling_windows,
    build_spy_benchmark,
    compute_performance_metrics,
    run_rolling_backtest,
)
from strategy.data import (  # noqa: E402
    build_xy_returns,
    fill_missing_with_reference,
    get_feature_columns,
    load_market_data,
    preprocess_data,
    save_market_data,
    slice_by_date,
)
from strategy.model import (  # noqa: E402
    fit_random_forest,
    select_positive_importance_features,
    sequential_feature_selection,
    tune_random_forest,
)
from strategy.portfolio import (  # noqa: E402
    PortfolioConfig,
    build_portfolio_weights,
    build_signal_scores,
    compute_period_return_from_weights,
)


@dataclass
class SegmentSpec:
    name: str
    train_start: str
    train_end: str
    valid_start: str
    valid_end: str
    rolling_start: str
    rolling_windows: int


@dataclass
class SegmentFitResult:
    feature_columns: list[str]
    model_params: dict[str, Any]
    validation_profit: float
    validation_turnover: float
    validation_active_names: int
    tuning_best_value: float
    selection_history: pd.DataFrame | None


@dataclass
class HoldoutResult:
    model_segment: str
    train_start: str
    train_end: str
    holdout_start: str
    holdout_end: str
    strategy_nav: pd.Series
    spy_nav: pd.Series
    strategy_returns: pd.Series
    spy_returns: pd.Series
    strategy_turnover: pd.Series
    active_names: pd.Series
    period_ic: pd.Series
    period_rank_ic: pd.Series
    metrics: dict[str, float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run random-forest rolling backtest.")
    parser.add_argument("--data", required=True, help="Input data file (.pkl/.parquet).")
    parser.add_argument("--output-dir", default="artifacts/backtest", help="Output directory.")
    parser.add_argument(
        "--label-source",
        choices=["actual", "pred_rel_return"],
        default="actual",
        help="Label source; 'actual' uses next_period_return - spy_next_period_return.",
    )
    parser.add_argument("--label-threshold", type=float, default=0.05)
    parser.add_argument("--add-missing-indicators", action="store_true")
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--portfolio-min-score", type=float, default=0.05)
    parser.add_argument("--portfolio-winsor-z", type=float, default=3.0)
    parser.add_argument("--portfolio-gross-target", type=float, default=1.0)
    parser.add_argument("--portfolio-net-target", type=float, default=0.0)
    parser.add_argument("--portfolio-max-name-weight", type=float, default=0.02)
    parser.add_argument("--portfolio-min-names-per-side", type=int, default=5)
    parser.add_argument(
        "--portfolio-vol-scaling",
        choices=["on", "off"],
        default="on",
        help="Use train-window volatility scaling in portfolio construction.",
    )
    parser.add_argument("--portfolio-vol-power", type=float, default=1.0)
    parser.add_argument(
        "--portfolio-sector-neutral",
        choices=["on", "off"],
        default="off",
        help="Apply coarse sector de-meaning using one-hot sector columns.",
    )
    parser.add_argument("--portfolio-sector-prefix", default="SP_sector_code_")
    parser.add_argument("--n-trials", type=int, default=50)
    parser.add_argument(
        "--tuning-cv-folds",
        type=int,
        default=1,
        help="If >1, tune RF with expanding time-series CV folds on the training window.",
    )
    parser.add_argument(
        "--feature-selection",
        choices=["none", "importance", "sequential"],
        default="importance",
    )
    parser.add_argument("--min-features", type=int, default=2)
    parser.add_argument("--max-selection-steps", type=int, default=200)
    parser.add_argument("--random-seed", type=int, default=123)
    parser.add_argument("--train-months", type=int, default=60)
    parser.add_argument("--gap-months", type=int, default=3)
    parser.add_argument("--test-months", type=int, default=3)
    parser.add_argument("--segment1-start", default="2004-04-01")
    parser.add_argument("--segment1-windows", type=int, default=60)
    parser.add_argument("--segment2-start", default="2009-04-01")
    parser.add_argument("--segment2-windows", type=int, default=20)
    parser.add_argument(
        "--holdout-start",
        default="",
        help="Optional final holdout start date (inclusive). Requires --holdout-end.",
    )
    parser.add_argument(
        "--holdout-end",
        default="",
        help="Optional final holdout end date (inclusive). Requires --holdout-start.",
    )
    parser.add_argument(
        "--holdout-model-segment",
        choices=["segment_a", "segment_b"],
        default="segment_b",
        help="Which segment's selected features/params to use for final holdout model.",
    )
    parser.add_argument(
        "--export-parquet",
        default="",
        help="Optional path to save the cleaned dataset as parquet.",
    )
    return parser.parse_args()


def build_portfolio_config(args: argparse.Namespace) -> PortfolioConfig:
    return PortfolioConfig(
        min_score=float(args.portfolio_min_score),
        winsor_z=float(args.portfolio_winsor_z),
        use_prob_signal=True,
        gross_target=float(args.portfolio_gross_target),
        net_target=float(args.portfolio_net_target),
        max_name_weight=float(args.portfolio_max_name_weight),
        min_names_per_side=int(args.portfolio_min_names_per_side),
        use_vol_scaling=args.portfolio_vol_scaling == "on",
        vol_power=float(args.portfolio_vol_power),
        sector_neutral=args.portfolio_sector_neutral == "on",
        sector_prefix=str(args.portfolio_sector_prefix),
    )


def fit_segment_model(
    frame: pd.DataFrame,
    spec: SegmentSpec,
    args: argparse.Namespace,
    portfolio_cfg: PortfolioConfig,
    seed_offset: int = 0,
) -> SegmentFitResult:
    train_raw = slice_by_date(frame, spec.train_start, spec.train_end)
    valid_raw = slice_by_date(frame, spec.valid_start, spec.valid_end)
    if train_raw.empty or valid_raw.empty:
        raise ValueError(f"Segment {spec.name} has empty train/valid frame.")

    train_frame = fill_missing_with_reference(
        frame=train_raw,
        reference=train_raw,
        add_missing_indicators=args.add_missing_indicators,
    )
    valid_frame = fill_missing_with_reference(
        frame=valid_raw,
        reference=train_raw,
        add_missing_indicators=args.add_missing_indicators,
    )

    feature_columns = get_feature_columns(train_frame)
    train_x, train_y, train_returns = build_xy_returns(train_frame, feature_columns)
    valid_x, _, valid_returns = build_xy_returns(valid_frame, feature_columns)

    seed = args.random_seed + seed_offset
    best_params, best_value = tune_random_forest(
        train_x=train_x,
        train_y=train_y,
        train_returns=train_returns,
        valid_x=valid_x,
        valid_returns=valid_returns,
        n_trials=args.n_trials,
        random_state=seed,
        cost_bps=args.cost_bps,
        tuning_cv_folds=args.tuning_cv_folds,
    )

    selected_features = feature_columns
    selection_history: pd.DataFrame | None = None
    if args.feature_selection == "importance":
        model = fit_random_forest(train_x, train_y, params=best_params, random_state=seed)
        selected_features = select_positive_importance_features(model, feature_columns)
    elif args.feature_selection == "sequential":
        selection = sequential_feature_selection(
            train_x=train_x,
            train_y=train_y,
            valid_x=valid_x,
            valid_returns=valid_returns,
            params=best_params,
            random_state=seed,
            min_features=args.min_features,
            max_steps=args.max_selection_steps,
            cost_bps=args.cost_bps,
        )
        selected_features = selection.selected_features
        selection_history = selection.history

    train_sel = train_x[selected_features]
    valid_sel = valid_x[selected_features]
    model = fit_random_forest(train_sel, train_y, params=best_params, random_state=seed)
    valid_preds = model.predict(valid_sel)
    valid_probs: np.ndarray | None = None
    valid_classes: np.ndarray | None = None
    if portfolio_cfg.use_prob_signal and hasattr(model, "predict_proba"):
        valid_probs = model.predict_proba(valid_sel)
        valid_classes = getattr(model, "classes_", None)

    valid_weights = build_portfolio_weights(
        predictions=valid_preds,
        probs=valid_probs,
        classes_=valid_classes,
        sample_index=valid_sel.index,
        train_frame=train_frame,
        test_frame=valid_frame,
        cfg=portfolio_cfg,
    )
    valid_profit, _, valid_turnover = compute_period_return_from_weights(
        weights=valid_weights,
        realized_returns=valid_returns,
        sample_index=valid_sel.index,
        cost_bps=args.cost_bps,
        previous_weights=None,
    )
    active_names = int(len(valid_weights))

    return SegmentFitResult(
        feature_columns=selected_features,
        model_params=best_params,
        validation_profit=valid_profit,
        validation_turnover=valid_turnover,
        validation_active_names=active_names,
        tuning_best_value=best_value,
        selection_history=selection_history,
    )


def combine_backtest_segments(
    first_series: pd.Series,
    second_series: pd.Series,
    name: str,
) -> pd.Series:
    if first_series.empty:
        out = second_series.copy()
        out.name = name
        return out
    if second_series.empty:
        out = first_series.copy()
        out.name = name
        return out

    combined = pd.concat([first_series, second_series]).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    combined.name = name
    return combined


def _safe_corr(signal: pd.Series, target: pd.Series, method: str) -> float:
    aligned = pd.concat([signal.rename("signal"), target.rename("target")], axis=1).dropna()
    if len(aligned) < 2:
        return float("nan")
    if aligned["signal"].nunique() < 2 or aligned["target"].nunique() < 2:
        return float("nan")
    value = aligned["signal"].corr(aligned["target"], method=method)
    return float(value) if pd.notna(value) else float("nan")


def _period_ic(
    predictions: np.ndarray,
    realized_returns: np.ndarray,
    sample_index: pd.Index,
) -> tuple[float, float]:
    signal = pd.Series(predictions, index=sample_index, dtype=float)
    realized = pd.Series(realized_returns, index=sample_index, dtype=float)
    if isinstance(sample_index, pd.MultiIndex) and "ticker" in sample_index.names:
        signal = signal.groupby(level="ticker", sort=False).last()
        realized = realized.groupby(level="ticker", sort=False).last()
    period_ic = _safe_corr(signal, realized, method="pearson")
    period_rank_ic = _safe_corr(signal, realized, method="spearman")
    return period_ic, period_rank_ic


def _periods_per_year_from_test_months(test_months: int) -> float:
    if test_months < 1:
        raise ValueError("--test-months must be >= 1.")
    return 12.0 / float(test_months)


def _build_holdout_period_ranges(
    holdout_start: pd.Timestamp,
    holdout_end: pd.Timestamp,
    test_months: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if test_months < 1:
        raise ValueError("--test-months must be >= 1.")

    ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    period_start = holdout_start
    while period_start <= holdout_end:
        next_start = period_start + pd.DateOffset(months=test_months)
        period_end = min(next_start - pd.Timedelta(days=1), holdout_end)
        ranges.append((period_start, period_end))
        period_start = next_start
    return ranges


def _resolve_period_date_from_index(sample_index: pd.Index, fallback: pd.Timestamp) -> pd.Timestamp:
    if isinstance(sample_index, pd.MultiIndex) and "date" in sample_index.names:
        last_date = sample_index.get_level_values("date").max()
        if pd.notna(last_date):
            return pd.Timestamp(last_date)
    return pd.Timestamp(fallback)


def _build_holdout_result(
    frame: pd.DataFrame,
    holdout_start: str,
    holdout_end: str,
    model_segment: str,
    segment_fit: SegmentFitResult,
    args: argparse.Namespace,
    portfolio_cfg: PortfolioConfig,
) -> HoldoutResult:
    holdout_start_ts = pd.Timestamp(holdout_start)
    holdout_end_ts = pd.Timestamp(holdout_end)
    if holdout_start_ts > holdout_end_ts:
        raise ValueError("--holdout-start must be <= --holdout-end.")

    date_values = pd.Index(frame.index.get_level_values("date"))
    train_mask = date_values < holdout_start_ts
    train_raw = frame.loc[train_mask]
    holdout_raw = slice_by_date(frame, holdout_start, holdout_end)
    if train_raw.empty:
        raise ValueError("Holdout training frame is empty; choose a later --holdout-start.")
    if holdout_raw.empty:
        raise ValueError("Holdout frame is empty; adjust --holdout-start/--holdout-end.")

    train_frame = fill_missing_with_reference(
        frame=train_raw,
        reference=train_raw,
        add_missing_indicators=args.add_missing_indicators,
    )
    holdout_frame = fill_missing_with_reference(
        frame=holdout_raw,
        reference=train_raw,
        add_missing_indicators=args.add_missing_indicators,
    )
    feature_columns = list(segment_fit.feature_columns)
    for col in feature_columns:
        if col not in train_frame.columns:
            train_frame[col] = 0.0
        if col not in holdout_frame.columns:
            holdout_frame[col] = 0.0

    train_x, train_y, _ = build_xy_returns(train_frame, feature_columns)
    holdout_x, _, holdout_returns = build_xy_returns(holdout_frame, feature_columns)
    if train_x.empty or holdout_x.empty:
        raise ValueError("Holdout train/test matrix is empty; check date ranges and features.")

    model = fit_random_forest(
        train_x=train_x,
        train_y=train_y,
        params=segment_fit.model_params,
        random_state=args.random_seed + 4000,
    )
    holdout_preds = model.predict(holdout_x)
    holdout_probs: np.ndarray | None = None
    holdout_classes: np.ndarray | None = None
    if portfolio_cfg.use_prob_signal and hasattr(model, "predict_proba"):
        holdout_probs = model.predict_proba(holdout_x)
        holdout_classes = getattr(model, "classes_", None)

    period_dates: list[pd.Timestamp] = []
    period_returns: list[float] = []
    period_turnover: list[float] = []
    period_active_names: list[int] = []
    period_ic_values: list[float] = []
    period_rank_ic_values: list[float] = []
    nav_points: list[float] = []
    nav_value = 1.0
    previous_weights: pd.Series | None = None

    holdout_date_values = pd.Index(holdout_x.index.get_level_values("date"))
    holdout_periods = _build_holdout_period_ranges(
        holdout_start=holdout_start_ts,
        holdout_end=holdout_end_ts,
        test_months=args.test_months,
    )
    for period_start, period_end in holdout_periods:
        mask = (holdout_date_values >= period_start) & (holdout_date_values <= period_end)
        if not np.any(mask):
            continue
        idx = holdout_x.index[mask]
        preds = holdout_preds[mask]
        probs = holdout_probs[mask] if holdout_probs is not None else None
        realized = holdout_returns[mask]

        period_weights = build_portfolio_weights(
            predictions=preds,
            probs=probs,
            classes_=holdout_classes,
            sample_index=idx,
            train_frame=train_frame,
            test_frame=holdout_frame.loc[idx],
            cfg=portfolio_cfg,
        )
        period_profit, current_weights, turnover = compute_period_return_from_weights(
            weights=period_weights,
            realized_returns=realized,
            sample_index=idx,
            cost_bps=args.cost_bps,
            previous_weights=previous_weights,
        )
        previous_weights = current_weights
        period_signal = build_signal_scores(
            predictions=preds,
            probs=probs,
            classes_=holdout_classes,
            use_prob_signal=portfolio_cfg.use_prob_signal,
        )
        ic_value, rank_ic_value = _period_ic(
            predictions=period_signal,
            realized_returns=realized,
            sample_index=idx,
        )
        nav_value *= 1.0 + period_profit
        nav_points.append(nav_value)
        period_dates.append(_resolve_period_date_from_index(idx, fallback=period_end))
        period_returns.append(float(period_profit))
        period_turnover.append(float(turnover))
        period_active_names.append(int(len(current_weights)))
        period_ic_values.append(float(ic_value))
        period_rank_ic_values.append(float(rank_ic_value))

    strategy_nav = pd.Series(nav_points, index=period_dates, name="strategy_nav")
    strategy_returns = pd.Series(period_returns, index=period_dates, name="strategy_ret")
    strategy_turnover = pd.Series(period_turnover, index=period_dates, name="strategy_turnover")
    active_names = pd.Series(period_active_names, index=period_dates, name="active_names")
    period_ic_series = pd.Series(period_ic_values, index=period_dates, name="period_ic")
    period_rank_ic_series = pd.Series(period_rank_ic_values, index=period_dates, name="period_rank_ic")
    spy_nav = build_spy_benchmark(frame, strategy_nav.index)
    spy_returns = spy_nav.pct_change().dropna()
    periods_per_year = _periods_per_year_from_test_months(args.test_months)
    metrics = compute_performance_metrics(
        strategy_nav=strategy_nav,
        spy_nav=spy_nav,
        strategy_returns=strategy_returns,
        spy_returns=spy_returns,
        strategy_turnover=strategy_turnover,
        active_names=active_names,
        period_ic=period_ic_series,
        period_rank_ic=period_rank_ic_series,
        periods_per_year=periods_per_year,
    )

    train_start = pd.Timestamp(train_raw.index.get_level_values("date").min()).strftime("%Y-%m-%d")
    train_end = pd.Timestamp(train_raw.index.get_level_values("date").max()).strftime("%Y-%m-%d")
    return HoldoutResult(
        model_segment=model_segment,
        train_start=train_start,
        train_end=train_end,
        holdout_start=holdout_start_ts.strftime("%Y-%m-%d"),
        holdout_end=holdout_end_ts.strftime("%Y-%m-%d"),
        strategy_nav=strategy_nav,
        spy_nav=spy_nav,
        strategy_returns=strategy_returns,
        spy_returns=spy_returns,
        strategy_turnover=strategy_turnover,
        active_names=active_names,
        period_ic=period_ic_series,
        period_rank_ic=period_rank_ic_series,
        metrics=metrics,
    )


def _format_percent(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value * 100:.2f}%"


def _format_float(value: float, precision: int = 6) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:.{precision}f}"


def build_run_summary_text(
    strategy_nav: pd.Series,
    strategy_turnover: pd.Series,
    period_ic: pd.Series,
    period_rank_ic: pd.Series,
    segment_a: SegmentFitResult,
    segment_b: SegmentFitResult,
    metrics: dict[str, float],
    tuning_cv_folds: int,
    holdout_result: HoldoutResult | None,
) -> str:
    if strategy_nav.empty:
        date_span = "n/a -> n/a"
    else:
        start_date = pd.Timestamp(strategy_nav.index.min()).strftime("%Y-%m-%d")
        end_date = pd.Timestamp(strategy_nav.index.max()).strftime("%Y-%m-%d")
        date_span = f"{start_date} -> {end_date}"

    strategy_total_return = float(metrics.get("strategy_total_return", float("nan")))
    spy_total_return = float(metrics.get("spy_total_return", float("nan")))
    excess_total_return = strategy_total_return - spy_total_return
    if pd.isna(excess_total_return):
        relative_result = "n/a"
    elif excess_total_return > 0:
        relative_result = f"Outperformed SPY by {_format_percent(excess_total_return)}."
    elif excess_total_return < 0:
        relative_result = f"Underperformed SPY by {_format_percent(abs(excess_total_return))}."
    else:
        relative_result = "Matched SPY total return."

    non_na_ic_points = int(period_ic.notna().sum()) if not period_ic.empty else 0
    non_na_rank_ic_points = int(period_rank_ic.notna().sum()) if not period_rank_ic.empty else 0
    if tuning_cv_folds > 1:
        tuning_line = f"Time-series CV tuning: enabled ({tuning_cv_folds} expanding folds)."
    else:
        tuning_line = "Time-series CV tuning: disabled (single validation slice)."

    lines = [
        "Backtest run summary",
        f"Date span: {date_span}",
        f"NAV points: {len(strategy_nav)}",
        "Evaluation protocol: walk-forward OOS rolling backtest (segment A + segment B).",
        tuning_line,
        "",
        "Performance vs SPY",
        f"- Strategy total return: {_format_percent(strategy_total_return)}",
        f"- SPY total return: {_format_percent(spy_total_return)}",
        f"- Relative result: {relative_result}",
        f"- Strategy annualized return: {_format_percent(float(metrics.get('strategy_annualized_return', float('nan'))))}",
        f"- SPY annualized return: {_format_percent(float(metrics.get('spy_annualized_return', float('nan'))))}",
        f"- Strategy annualized volatility: {_format_percent(float(metrics.get('strategy_annualized_volatility', float('nan'))))}",
        f"- SPY annualized volatility: {_format_percent(float(metrics.get('spy_annualized_volatility', float('nan'))))}",
        f"- Strategy sharpe: {_format_float(float(metrics.get('strategy_sharpe', float('nan'))))}",
        f"- SPY sharpe: {_format_float(float(metrics.get('spy_sharpe', float('nan'))))}",
        f"- Strategy sortino: {_format_float(float(metrics.get('strategy_sortino', float('nan'))))}",
        f"- Strategy calmar: {_format_float(float(metrics.get('strategy_calmar', float('nan'))))}",
        f"- Alpha: {_format_float(float(metrics.get('alpha', float('nan'))))}",
        f"- Beta: {_format_float(float(metrics.get('beta', float('nan'))))}",
        f"- Information ratio: {_format_float(float(metrics.get('information_ratio', float('nan'))))}",
        f"- Hedged sharpe: {_format_float(float(metrics.get('hedged_sharpe', float('nan'))))}",
        f"- Max drawdown (strategy): {_format_percent(float(metrics.get('strategy_max_drawdown', float('nan'))))}",
        f"- Max drawdown (SPY): {_format_percent(float(metrics.get('spy_max_drawdown', float('nan'))))}",
        f"- Period win rate vs SPY: {_format_percent(float(metrics.get('win_rate_vs_spy', float('nan'))))}",
        f"- Average excess return per period: {_format_percent(float(metrics.get('avg_excess_return_per_period', float('nan'))))}",
        f"- Tracking error annualized: {_format_percent(float(metrics.get('tracking_error_annualized', float('nan'))))}",
        "",
        "Tail / Distribution",
        f"- Strategy VaR 95%: {_format_percent(float(metrics.get('strategy_var_95', float('nan'))))}",
        f"- Strategy CVaR 95%: {_format_percent(float(metrics.get('strategy_cvar_95', float('nan'))))}",
        f"- SPY VaR 95%: {_format_percent(float(metrics.get('spy_var_95', float('nan'))))}",
        f"- SPY CVaR 95%: {_format_percent(float(metrics.get('spy_cvar_95', float('nan'))))}",
        f"- Strategy skew / kurtosis: {_format_float(float(metrics.get('strategy_skew', float('nan'))))} / {_format_float(float(metrics.get('strategy_kurtosis', float('nan'))))}",
        f"- SPY skew / kurtosis: {_format_float(float(metrics.get('spy_skew', float('nan'))))} / {_format_float(float(metrics.get('spy_kurtosis', float('nan'))))}",
        "",
        "Turnover / Breadth / IC",
        f"- Avg turnover per period: {_format_float(float(metrics.get('avg_turnover_per_period', float('nan'))))}",
        f"- Annualized turnover (approx): {_format_float(float(metrics.get('annualized_turnover', float('nan'))))}",
        f"- Avg active names: {_format_float(float(metrics.get('avg_active_names', float('nan'))), precision=2)}",
        f"- IC mean / IR / positive rate: {_format_float(float(metrics.get('ic_mean', float('nan'))))} / {_format_float(float(metrics.get('ic_ir', float('nan'))))} / {_format_percent(float(metrics.get('ic_positive_rate', float('nan'))))}",
        f"- Rank IC mean / IR / positive rate: {_format_float(float(metrics.get('rank_ic_mean', float('nan'))))} / {_format_float(float(metrics.get('rank_ic_ir', float('nan'))))} / {_format_percent(float(metrics.get('rank_ic_positive_rate', float('nan'))))}",
        f"- IC data points: {non_na_ic_points}, Rank IC data points: {non_na_rank_ic_points}",
        f"- Turnover data points: {len(strategy_turnover.dropna())}",
        "",
        "Segment diagnostics",
        (
            "- Segment A: "
            f"features={len(segment_a.feature_columns)}, "
            f"tuning_best={_format_float(segment_a.tuning_best_value)}, "
            f"validation_profit={_format_float(segment_a.validation_profit)}, "
            f"validation_turnover={_format_float(segment_a.validation_turnover)}, "
            f"active_names={segment_a.validation_active_names}"
        ),
        (
            "- Segment B: "
            f"features={len(segment_b.feature_columns)}, "
            f"tuning_best={_format_float(segment_b.tuning_best_value)}, "
            f"validation_profit={_format_float(segment_b.validation_profit)}, "
            f"validation_turnover={_format_float(segment_b.validation_turnover)}, "
            f"active_names={segment_b.validation_active_names}"
        ),
        "",
        "Artifacts",
        "- OOS period-level diagnostics are exported to oos_period_diagnostics.csv.",
    ]

    if holdout_result is not None:
        hm = holdout_result.metrics
        overlap_note = "- Holdout overlap note: n/a (main backtest window is empty)."
        if not strategy_nav.empty:
            main_start = pd.Timestamp(strategy_nav.index.min())
            main_end = pd.Timestamp(strategy_nav.index.max())
            holdout_start_ts = pd.Timestamp(holdout_result.holdout_start)
            holdout_end_ts = pd.Timestamp(holdout_result.holdout_end)
            has_overlap = holdout_start_ts <= main_end and holdout_end_ts >= main_start
            if has_overlap:
                overlap_note = (
                    "- Holdout overlap note: holdout window overlaps the main backtest window."
                )
            else:
                overlap_note = "- Holdout overlap note: no overlap with main backtest window."
        lines.extend(
            [
                "",
                "Final Holdout OOS",
                f"- Holdout date span: {holdout_result.holdout_start} -> {holdout_result.holdout_end}",
                f"- Holdout training span: {holdout_result.train_start} -> {holdout_result.train_end}",
                f"- Holdout model source: {holdout_result.model_segment}",
                f"- Holdout strategy total return: {_format_percent(float(hm.get('strategy_total_return', float('nan'))))}",
                f"- Holdout SPY total return: {_format_percent(float(hm.get('spy_total_return', float('nan'))))}",
                f"- Holdout strategy annualized return: {_format_percent(float(hm.get('strategy_annualized_return', float('nan'))))}",
                f"- Holdout sharpe / sortino / calmar: {_format_float(float(hm.get('strategy_sharpe', float('nan'))))} / {_format_float(float(hm.get('strategy_sortino', float('nan'))))} / {_format_float(float(hm.get('strategy_calmar', float('nan'))))}",
                f"- Holdout max drawdown: {_format_percent(float(hm.get('strategy_max_drawdown', float('nan'))))}",
                f"- Holdout VaR95 / CVaR95: {_format_percent(float(hm.get('strategy_var_95', float('nan'))))} / {_format_percent(float(hm.get('strategy_cvar_95', float('nan'))))}",
                f"- Holdout avg turnover: {_format_float(float(hm.get('avg_turnover_per_period', float('nan'))))}",
                f"- Holdout IC mean / Rank IC mean: {_format_float(float(hm.get('ic_mean', float('nan'))))} / {_format_float(float(hm.get('rank_ic_mean', float('nan'))))}",
                overlap_note,
                "- Holdout artifacts are exported to holdout/*.csv and holdout/metrics.json.",
            ]
        )

    return "\n".join(lines)


def write_outputs(
    out_dir: Path,
    strategy_nav: pd.Series,
    spy_nav: pd.Series,
    strategy_returns: pd.Series,
    spy_returns: pd.Series,
    strategy_turnover: pd.Series,
    active_names: pd.Series,
    period_ic: pd.Series,
    period_rank_ic: pd.Series,
    segment_a: SegmentFitResult,
    segment_b: SegmentFitResult,
    metrics: dict[str, float],
    run_config: dict[str, Any],
    run_summary_text: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    strategy_nav.to_frame(name="strategy_nav").to_csv(out_dir / "strategy_nav.csv")
    spy_nav.to_frame(name="spy_nav").to_csv(out_dir / "spy_nav.csv")
    strategy_returns.to_frame(name="strategy_ret").to_csv(out_dir / "strategy_returns.csv")
    spy_returns.to_frame(name="spy_ret").to_csv(out_dir / "spy_returns.csv")
    strategy_turnover.to_frame(name="strategy_turnover").to_csv(out_dir / "strategy_turnover.csv")
    active_names.to_frame(name="active_names").to_csv(out_dir / "active_names.csv")
    pd.concat([period_ic, period_rank_ic], axis=1).to_csv(out_dir / "ic_series.csv")
    pd.concat([strategy_nav, spy_nav], axis=1).to_csv(out_dir / "strategy_vs_spy.csv")
    pd.concat(
        [
            strategy_returns.rename("strategy_ret"),
            spy_returns.rename("spy_ret"),
            strategy_turnover.rename("strategy_turnover"),
            active_names.rename("active_names"),
            period_ic.rename("period_ic"),
            period_rank_ic.rename("period_rank_ic"),
        ],
        axis=1,
    ).to_csv(out_dir / "oos_period_diagnostics.csv")

    summary = {
        "segment_a_validation_profit": segment_a.validation_profit,
        "segment_a_validation_turnover": segment_a.validation_turnover,
        "segment_a_validation_active_names": segment_a.validation_active_names,
        "segment_a_tuning_best_value": segment_a.tuning_best_value,
        "segment_a_feature_count": len(segment_a.feature_columns),
        "segment_b_validation_profit": segment_b.validation_profit,
        "segment_b_validation_turnover": segment_b.validation_turnover,
        "segment_b_validation_active_names": segment_b.validation_active_names,
        "segment_b_tuning_best_value": segment_b.tuning_best_value,
        "segment_b_feature_count": len(segment_b.feature_columns),
    }
    summary.update(metrics)
    (out_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "run_config.json").write_text(json.dumps(run_config, indent=2), encoding="utf-8")
    (out_dir / "run_summary.txt").write_text(run_summary_text + "\n", encoding="utf-8")

    (out_dir / "segment_a_features.txt").write_text(
        "\n".join(segment_a.feature_columns), encoding="utf-8"
    )
    (out_dir / "segment_b_features.txt").write_text(
        "\n".join(segment_b.feature_columns), encoding="utf-8"
    )

    if segment_a.selection_history is not None and not segment_a.selection_history.empty:
        segment_a.selection_history.to_csv(out_dir / "segment_a_selection_history.csv", index=False)
    if segment_b.selection_history is not None and not segment_b.selection_history.empty:
        segment_b.selection_history.to_csv(out_dir / "segment_b_selection_history.csv", index=False)


def write_holdout_outputs(out_dir: Path, holdout: HoldoutResult) -> None:
    holdout_dir = out_dir / "holdout"
    holdout_dir.mkdir(parents=True, exist_ok=True)

    holdout.strategy_nav.to_frame(name="strategy_nav").to_csv(holdout_dir / "strategy_nav.csv")
    holdout.spy_nav.to_frame(name="spy_nav").to_csv(holdout_dir / "spy_nav.csv")
    holdout.strategy_returns.to_frame(name="strategy_ret").to_csv(holdout_dir / "strategy_returns.csv")
    holdout.spy_returns.to_frame(name="spy_ret").to_csv(holdout_dir / "spy_returns.csv")
    holdout.strategy_turnover.to_frame(name="strategy_turnover").to_csv(
        holdout_dir / "strategy_turnover.csv"
    )
    holdout.active_names.to_frame(name="active_names").to_csv(holdout_dir / "active_names.csv")
    pd.concat([holdout.period_ic, holdout.period_rank_ic], axis=1).to_csv(holdout_dir / "ic_series.csv")
    pd.concat([holdout.strategy_nav, holdout.spy_nav], axis=1).to_csv(holdout_dir / "strategy_vs_spy.csv")
    pd.concat(
        [
            holdout.strategy_returns.rename("strategy_ret"),
            holdout.spy_returns.rename("spy_ret"),
            holdout.strategy_turnover.rename("strategy_turnover"),
            holdout.active_names.rename("active_names"),
            holdout.period_ic.rename("period_ic"),
            holdout.period_rank_ic.rename("period_rank_ic"),
        ],
        axis=1,
    ).to_csv(holdout_dir / "oos_period_diagnostics.csv")
    (holdout_dir / "metrics.json").write_text(json.dumps(holdout.metrics, indent=2), encoding="utf-8")
    (holdout_dir / "holdout_config.json").write_text(
        json.dumps(
            {
                "model_segment": holdout.model_segment,
                "train_start": holdout.train_start,
                "train_end": holdout.train_end,
                "holdout_start": holdout.holdout_start,
                "holdout_end": holdout.holdout_end,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def resolve_git_commit(root: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    commit = out.strip()
    return commit or None


def build_run_config(
    args: argparse.Namespace,
    segment_a_spec: SegmentSpec,
    segment_b_spec: SegmentSpec,
    holdout_result: HoldoutResult | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "resolved_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": resolve_git_commit(ROOT),
        "arguments": vars(args),
        "segment_specs": {
            "segment_a": asdict(segment_a_spec),
            "segment_b": asdict(segment_b_spec),
        },
    }
    if holdout_result is not None:
        config["holdout"] = {
            "enabled": True,
            "model_segment": holdout_result.model_segment,
            "train_start": holdout_result.train_start,
            "train_end": holdout_result.train_end,
            "holdout_start": holdout_result.holdout_start,
            "holdout_end": holdout_result.holdout_end,
            "n_periods": int(len(holdout_result.strategy_returns)),
        }
    else:
        config["holdout"] = {"enabled": False}
    return config


def main() -> None:
    args = parse_args()
    if args.tuning_cv_folds < 1:
        raise ValueError("--tuning-cv-folds must be >= 1.")
    if args.test_months < 1:
        raise ValueError("--test-months must be >= 1.")
    if bool(args.holdout_start) != bool(args.holdout_end):
        raise ValueError("Use --holdout-start and --holdout-end together.")
    portfolio_cfg = build_portfolio_config(args)

    raw = load_market_data(args.data)
    frame = preprocess_data(
        raw,
        label_source=args.label_source,
        label_threshold=args.label_threshold,
        add_missing_indicators=False,
        apply_global_fill=False,
    )
    if args.export_parquet:
        export_frame = preprocess_data(
            raw,
            label_source=args.label_source,
            label_threshold=args.label_threshold,
            add_missing_indicators=args.add_missing_indicators,
            apply_global_fill=True,
        )
        save_market_data(export_frame, args.export_parquet)

    segment_a_spec = SegmentSpec(
        name="segment_a",
        train_start="2004-01-01",
        train_end="2009-01-01",
        valid_start="2009-04-01",
        valid_end="2009-07-01",
        rolling_start=args.segment1_start,
        rolling_windows=args.segment1_windows,
    )
    segment_b_spec = SegmentSpec(
        name="segment_b",
        train_start="2009-01-01",
        train_end="2014-01-01",
        valid_start="2014-04-01",
        valid_end="2014-07-01",
        rolling_start=args.segment2_start,
        rolling_windows=args.segment2_windows,
    )

    segment_a = fit_segment_model(
        frame=frame,
        spec=segment_a_spec,
        args=args,
        portfolio_cfg=portfolio_cfg,
        seed_offset=0,
    )
    segment_b = fit_segment_model(
        frame=frame,
        spec=segment_b_spec,
        args=args,
        portfolio_cfg=portfolio_cfg,
        seed_offset=1000,
    )

    windows_a = build_rolling_windows(
        start_date=segment_a_spec.rolling_start,
        n_windows=segment_a_spec.rolling_windows,
        train_months=args.train_months,
        gap_months=args.gap_months,
        test_months=args.test_months,
    )
    bt_a = run_rolling_backtest(
        frame=frame,
        windows=windows_a,
        feature_columns=segment_a.feature_columns,
        model_params=segment_a.model_params,
        random_state=args.random_seed,
        cost_bps=args.cost_bps,
        initial_nav=1.0,
        add_missing_indicators=args.add_missing_indicators,
        portfolio_config=portfolio_cfg,
    )

    initial_nav = float(bt_a.nav.iloc[-1]) if not bt_a.nav.empty else 1.0
    windows_b = build_rolling_windows(
        start_date=segment_b_spec.rolling_start,
        n_windows=segment_b_spec.rolling_windows,
        train_months=args.train_months,
        gap_months=args.gap_months,
        test_months=args.test_months,
    )
    bt_b = run_rolling_backtest(
        frame=frame,
        windows=windows_b,
        feature_columns=segment_b.feature_columns,
        model_params=segment_b.model_params,
        random_state=args.random_seed + 2000,
        cost_bps=args.cost_bps,
        initial_nav=initial_nav,
        add_missing_indicators=args.add_missing_indicators,
        portfolio_config=portfolio_cfg,
    )

    strategy_nav = combine_backtest_segments(bt_a.nav, bt_b.nav, name="strategy_nav")
    strategy_returns = combine_backtest_segments(
        bt_a.period_returns,
        bt_b.period_returns,
        name="strategy_ret",
    )
    strategy_turnover = combine_backtest_segments(
        bt_a.period_turnover,
        bt_b.period_turnover,
        name="strategy_turnover",
    )
    active_names = combine_backtest_segments(
        bt_a.active_names,
        bt_b.active_names,
        name="active_names",
    )
    period_ic = combine_backtest_segments(bt_a.period_ic, bt_b.period_ic, name="period_ic")
    period_rank_ic = combine_backtest_segments(
        bt_a.period_rank_ic,
        bt_b.period_rank_ic,
        name="period_rank_ic",
    )
    spy_nav = build_spy_benchmark(frame, strategy_nav.index)
    spy_returns = spy_nav.pct_change().dropna()
    periods_per_year = _periods_per_year_from_test_months(args.test_months)
    metrics = compute_performance_metrics(
        strategy_nav,
        spy_nav,
        strategy_returns=strategy_returns,
        spy_returns=spy_returns,
        strategy_turnover=strategy_turnover,
        active_names=active_names,
        period_ic=period_ic,
        period_rank_ic=period_rank_ic,
        periods_per_year=periods_per_year,
    )
    holdout_result: HoldoutResult | None = None
    if args.holdout_start and args.holdout_end:
        holdout_segment_fit = segment_a if args.holdout_model_segment == "segment_a" else segment_b
        holdout_result = _build_holdout_result(
            frame=frame,
            holdout_start=args.holdout_start,
            holdout_end=args.holdout_end,
            model_segment=args.holdout_model_segment,
            segment_fit=holdout_segment_fit,
            args=args,
            portfolio_cfg=portfolio_cfg,
        )

    run_config = build_run_config(
        args,
        segment_a_spec=segment_a_spec,
        segment_b_spec=segment_b_spec,
        holdout_result=holdout_result,
    )
    run_summary_text = build_run_summary_text(
        strategy_nav=strategy_nav,
        strategy_turnover=strategy_turnover,
        period_ic=period_ic,
        period_rank_ic=period_rank_ic,
        segment_a=segment_a,
        segment_b=segment_b,
        metrics=metrics,
        tuning_cv_folds=args.tuning_cv_folds,
        holdout_result=holdout_result,
    )

    out_dir = Path(args.output_dir)
    write_outputs(
        out_dir=out_dir,
        strategy_nav=strategy_nav,
        spy_nav=spy_nav,
        strategy_returns=strategy_returns,
        spy_returns=spy_returns,
        strategy_turnover=strategy_turnover,
        active_names=active_names,
        period_ic=period_ic,
        period_rank_ic=period_rank_ic,
        segment_a=segment_a,
        segment_b=segment_b,
        metrics=metrics,
        run_config=run_config,
        run_summary_text=run_summary_text,
    )
    if holdout_result is not None:
        write_holdout_outputs(out_dir=out_dir, holdout=holdout_result)

    print(f"Output directory: {out_dir}")
    print(f"Segment A feature count: {len(segment_a.feature_columns)}")
    print(f"Segment B feature count: {len(segment_b.feature_columns)}")
    if holdout_result is not None:
        print(f"Holdout output directory: {out_dir / 'holdout'}")
    print()
    print(run_summary_text)
    print()
    if metrics:
        print(json.dumps(metrics, indent=2))
    else:
        print("No metrics were computed; verify strategy/benchmark date overlap.")


if __name__ == "__main__":
    main()
