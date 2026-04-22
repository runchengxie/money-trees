from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

import numpy as np
import pandas as pd

from treealpha.backtest import (
    build_rolling_windows,
    build_spy_benchmark,
    compute_performance_metrics,
    run_rolling_backtest,
)
from treealpha.config import BacktestSettings
from treealpha.data import (
    apply_feature_lag,
    build_xy_target_returns,
    fill_missing_with_reference,
    get_feature_columns,
    load_market_data,
    preprocess_data,
    save_market_data,
    slice_by_date,
)
from treealpha.markets import get_market_profile
from treealpha.models import get_model_adapter
from treealpha.portfolio import PortfolioConfig, build_portfolio_weights, compute_period_return_from_weights

ROOT = Path(__file__).resolve().parents[2]


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


def parse_legacy_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run treealpha rolling backtest.")
    parser.add_argument("--data", required=True, help="Input data file (.pkl/.parquet).")
    parser.add_argument("--output-dir", default="artifacts/backtest", help="Output directory.")
    parser.add_argument("--label-source", choices=["actual", "pred_rel_return"], default="actual")
    parser.add_argument("--label-threshold", type=float, default=0.05)
    parser.add_argument("--add-missing-indicators", action="store_true")
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--portfolio-min-score", type=float, default=0.05)
    parser.add_argument("--portfolio-winsor-z", type=float, default=3.0)
    parser.add_argument(
        "--portfolio-weighting-method",
        choices=["heuristic", "signal_risk_qp"],
        default="heuristic",
    )
    parser.add_argument("--portfolio-gross-target", type=float, default=1.0)
    parser.add_argument("--portfolio-net-target", type=float, default=0.0)
    parser.add_argument("--portfolio-max-name-weight", type=float, default=0.02)
    parser.add_argument("--portfolio-min-names-per-side", type=int, default=5)
    parser.add_argument("--portfolio-vol-scaling", choices=["on", "off"], default="on")
    parser.add_argument("--portfolio-vol-power", type=float, default=1.0)
    parser.add_argument("--portfolio-sector-neutral", choices=["on", "off"], default="off")
    parser.add_argument("--portfolio-sector-prefix", default="SP_sector_code_")
    parser.add_argument("--portfolio-qp-risk-aversion", type=float, default=10.0)
    parser.add_argument("--portfolio-qp-turnover-penalty", type=float, default=5.0)
    parser.add_argument("--portfolio-qp-cov-lookback", type=int, default=252)
    parser.add_argument("--portfolio-qp-cov-shrinkage", choices=["on", "off"], default="on")
    parser.add_argument("--portfolio-qp-cov-ridge", type=float, default=1e-6)
    parser.add_argument("--portfolio-qp-mu-clip", type=float, default=1.0)
    parser.add_argument("--portfolio-qp-max-names", type=int, default=300)
    parser.add_argument("--portfolio-qp-solver-max-iter", type=int, default=300)
    parser.add_argument("--portfolio-qp-solver-ftol", type=float, default=1e-9)
    parser.add_argument(
        "--portfolio-qp-fallback-to-heuristic",
        choices=["on", "off"],
        default="on",
    )
    parser.add_argument("--n-trials", type=int, default=50)
    parser.add_argument("--tuning-cv-folds", type=int, default=1)
    parser.add_argument(
        "--feature-selection",
        choices=["none", "importance", "sequential"],
        default="importance",
    )
    parser.add_argument("--min-features", type=int, default=2)
    parser.add_argument("--max-selection-steps", type=int, default=200)
    parser.add_argument("--random-seed", type=int, default=123)
    parser.add_argument("--feature-lag-periods", type=int, default=0)
    parser.add_argument("--train-months", type=int, default=60)
    parser.add_argument("--gap-months", type=int, default=3)
    parser.add_argument("--test-months", type=int, default=3)
    parser.add_argument("--segment1-start", default="2004-04-01")
    parser.add_argument("--segment1-windows", type=int, default=60)
    parser.add_argument("--segment2-start", default="2009-04-01")
    parser.add_argument("--segment2-windows", type=int, default=20)
    parser.add_argument("--holdout-start", default="")
    parser.add_argument("--holdout-end", default="")
    parser.add_argument(
        "--holdout-model-segment",
        choices=["segment_a", "segment_b"],
        default="segment_b",
    )
    parser.add_argument("--export-parquet", default="")
    return parser.parse_args(argv)


def build_portfolio_config(settings: BacktestSettings) -> PortfolioConfig:
    return PortfolioConfig(
        min_score=float(settings.portfolio_min_score),
        winsor_z=float(settings.portfolio_winsor_z),
        use_prob_signal=True,
        weighting_method=str(settings.portfolio_weighting_method),
        gross_target=float(settings.portfolio_gross_target),
        net_target=float(settings.portfolio_net_target),
        max_name_weight=float(settings.portfolio_max_name_weight),
        min_names_per_side=int(settings.portfolio_min_names_per_side),
        use_vol_scaling=settings.portfolio_vol_scaling == "on",
        vol_power=float(settings.portfolio_vol_power),
        qp_risk_aversion=float(settings.portfolio_qp_risk_aversion),
        qp_turnover_penalty=float(settings.portfolio_qp_turnover_penalty),
        qp_cov_lookback=int(settings.portfolio_qp_cov_lookback),
        qp_cov_shrinkage=settings.portfolio_qp_cov_shrinkage == "on",
        qp_cov_ridge=float(settings.portfolio_qp_cov_ridge),
        qp_mu_clip=float(settings.portfolio_qp_mu_clip),
        qp_max_names=int(settings.portfolio_qp_max_names),
        qp_solver_max_iter=int(settings.portfolio_qp_solver_max_iter),
        qp_solver_ftol=float(settings.portfolio_qp_solver_ftol),
        qp_fallback_to_heuristic=settings.portfolio_qp_fallback_to_heuristic == "on",
        sector_neutral=settings.portfolio_sector_neutral == "on",
        sector_prefix=str(settings.portfolio_sector_prefix),
    )


def fit_segment_model(
    *,
    frame: pd.DataFrame,
    spec: SegmentSpec,
    settings: BacktestSettings,
    portfolio_cfg: PortfolioConfig,
    model_adapter,
    market_profile,
    seed_offset: int = 0,
) -> SegmentFitResult:
    train_raw = market_profile.filter_tradable_frame(slice_by_date(frame, spec.train_start, spec.train_end))
    valid_raw = market_profile.filter_tradable_frame(slice_by_date(frame, spec.valid_start, spec.valid_end))
    if train_raw.empty or valid_raw.empty:
        raise ValueError(f"Segment {spec.name} has empty train/valid frame.")

    train_frame = fill_missing_with_reference(
        frame=train_raw,
        reference=train_raw,
        add_missing_indicators=settings.add_missing_indicators,
    )
    valid_frame = fill_missing_with_reference(
        frame=valid_raw,
        reference=train_raw,
        add_missing_indicators=settings.add_missing_indicators,
    )

    feature_columns = get_feature_columns(train_frame)
    train_x, train_y, train_returns = build_xy_target_returns(
        train_frame,
        feature_columns,
        target_column=model_adapter.training_target_column,
    )
    valid_x, _, valid_returns = build_xy_target_returns(
        valid_frame,
        feature_columns,
        target_column=model_adapter.training_target_column,
    )

    seed = settings.random_seed + seed_offset
    best_params, best_value = model_adapter.tune(
        train_x=train_x,
        train_y=train_y,
        train_returns=train_returns,
        valid_x=valid_x,
        valid_returns=valid_returns,
        n_trials=settings.n_trials,
        random_state=seed,
        cost_bps=settings.cost_bps,
        tuning_cv_folds=settings.tuning_cv_folds,
        base_params=settings.model_params,
    )

    selection = model_adapter.select_features(
        method=settings.feature_selection,
        train_x=train_x,
        train_y=train_y,
        valid_x=valid_x,
        valid_returns=valid_returns,
        params=best_params,
        random_state=seed,
        min_features=settings.min_features,
        max_steps=settings.max_selection_steps,
        cost_bps=settings.cost_bps,
    )
    selected_features = list(selection.selected_features)

    train_sel = train_x[selected_features]
    valid_sel = valid_x[selected_features]
    model = model_adapter.fit(
        train_x=train_sel,
        train_y=train_y,
        params=best_params,
        random_state=seed,
    )
    outputs = model_adapter.predict_outputs(model=model, features=valid_sel)
    valid_weights = build_portfolio_weights(
        predictions=outputs.predictions
        if outputs.predictions is not None
        else np.zeros(len(valid_sel), dtype=int),
        probs=outputs.probabilities,
        classes_=outputs.classes_,
        raw_scores=outputs.scores,
        sample_index=valid_sel.index,
        train_frame=train_frame,
        test_frame=valid_frame,
        cfg=portfolio_cfg,
        previous_weights=None,
    )
    valid_profit, _, valid_turnover = compute_period_return_from_weights(
        weights=valid_weights,
        realized_returns=valid_returns,
        sample_index=valid_sel.index,
        cost_bps=settings.cost_bps,
        previous_weights=None,
    )
    return SegmentFitResult(
        feature_columns=selected_features,
        model_params=best_params,
        validation_profit=valid_profit,
        validation_turnover=valid_turnover,
        validation_active_names=int(len(valid_weights)),
        tuning_best_value=best_value,
        selection_history=selection.history,
    )


def combine_backtest_segments(first_series: pd.Series, second_series: pd.Series, name: str) -> pd.Series:
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


def _period_ic(predictions: np.ndarray, realized_returns: np.ndarray, sample_index: pd.Index) -> tuple[float, float]:
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
    *,
    frame: pd.DataFrame,
    holdout_start: str,
    holdout_end: str,
    model_segment: str,
    segment_fit: SegmentFitResult,
    settings: BacktestSettings | None = None,
    args: argparse.Namespace | None = None,
    portfolio_cfg: PortfolioConfig,
    model_adapter=None,
    market_profile=None,
) -> HoldoutResult:
    holdout_start_ts = pd.Timestamp(holdout_start)
    holdout_end_ts = pd.Timestamp(holdout_end)
    if holdout_start_ts > holdout_end_ts:
        raise ValueError("--holdout-start must be <= --holdout-end.")
    if settings is None:
        if args is not None and hasattr(args, "data"):
            settings = BacktestSettings.from_legacy_args(args)
        else:
            settings = BacktestSettings(data="")
    if model_adapter is None:
        model_adapter = get_model_adapter("random_forest")
    if market_profile is None:
        market_profile = get_market_profile("us")

    date_values = pd.Index(frame.index.get_level_values("date"))
    train_raw = market_profile.filter_tradable_frame(frame.loc[date_values < holdout_start_ts])
    holdout_raw = market_profile.filter_tradable_frame(slice_by_date(frame, holdout_start, holdout_end))
    if train_raw.empty or holdout_raw.empty:
        raise ValueError("Holdout train/test frame is empty; adjust holdout dates.")

    train_frame = fill_missing_with_reference(
        frame=train_raw,
        reference=train_raw,
        add_missing_indicators=settings.add_missing_indicators,
    )
    holdout_frame = fill_missing_with_reference(
        frame=holdout_raw,
        reference=train_raw,
        add_missing_indicators=settings.add_missing_indicators,
    )
    feature_columns = list(segment_fit.feature_columns)
    for col in feature_columns:
        if col not in train_frame.columns:
            train_frame[col] = 0.0
        if col not in holdout_frame.columns:
            holdout_frame[col] = 0.0

    train_x, train_y, _ = build_xy_target_returns(
        train_frame,
        feature_columns,
        target_column=model_adapter.training_target_column,
    )
    holdout_x, _, holdout_returns = build_xy_target_returns(
        holdout_frame,
        feature_columns,
        target_column=model_adapter.training_target_column,
    )
    if train_x.empty or holdout_x.empty:
        raise ValueError("Holdout train/test matrix is empty; check date ranges and features.")

    model = model_adapter.fit(
        train_x=train_x,
        train_y=train_y,
        params=segment_fit.model_params,
        random_state=settings.random_seed + 4000,
    )
    outputs = model_adapter.predict_outputs(model=model, features=holdout_x)
    holdout_predictions = (
        outputs.predictions if outputs.predictions is not None else np.zeros(len(holdout_x), dtype=int)
    )
    holdout_probabilities = outputs.probabilities
    holdout_scores = outputs.scores

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

    for period_start, period_end in _build_holdout_period_ranges(
        holdout_start=holdout_start_ts,
        holdout_end=holdout_end_ts,
        test_months=settings.test_months,
    ):
        mask = (holdout_date_values >= period_start) & (holdout_date_values <= period_end)
        if not np.any(mask):
            continue
        idx = holdout_x.index[mask]
        period_weights = build_portfolio_weights(
            predictions=holdout_predictions[mask],
            probs=holdout_probabilities[mask] if holdout_probabilities is not None else None,
            classes_=outputs.classes_,
            raw_scores=holdout_scores[mask],
            sample_index=idx,
            train_frame=train_frame,
            test_frame=holdout_frame.loc[idx],
            cfg=portfolio_cfg,
            previous_weights=previous_weights,
        )
        period_profit, current_weights, turnover = compute_period_return_from_weights(
            weights=period_weights,
            realized_returns=holdout_returns[mask],
            sample_index=idx,
            cost_bps=settings.cost_bps,
            previous_weights=previous_weights,
        )
        previous_weights = current_weights
        ic_value, rank_ic_value = _period_ic(
            predictions=holdout_scores[mask],
            realized_returns=holdout_returns[mask],
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
    spy_nav = build_spy_benchmark(frame, strategy_nav.index, benchmark_cum_col="benchmark_cum_ret")
    spy_returns = spy_nav.pct_change().dropna()
    metrics = compute_performance_metrics(
        strategy_nav=strategy_nav,
        spy_nav=spy_nav,
        strategy_returns=strategy_returns,
        spy_returns=spy_returns,
        strategy_turnover=strategy_turnover,
        active_names=active_names,
        period_ic=period_ic_series,
        period_rank_ic=period_rank_ic_series,
        periods_per_year=_periods_per_year_from_test_months(settings.test_months),
    )
    return HoldoutResult(
        model_segment=model_segment,
        train_start=pd.Timestamp(train_raw.index.get_level_values("date").min()).strftime("%Y-%m-%d"),
        train_end=pd.Timestamp(train_raw.index.get_level_values("date").max()).strftime("%Y-%m-%d"),
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
    *,
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
        date_span = (
            f"{pd.Timestamp(strategy_nav.index.min()).strftime('%Y-%m-%d')} -> "
            f"{pd.Timestamp(strategy_nav.index.max()).strftime('%Y-%m-%d')}"
        )
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
        "Performance vs SPY",
        f"- Strategy total return: {_format_percent(strategy_total_return)}",
        f"- SPY total return: {_format_percent(spy_total_return)}",
        f"- Relative result: {relative_result}",
        f"- Strategy annualized return: {_format_percent(float(metrics.get('strategy_annualized_return', float('nan'))))}",
        f"- SPY annualized return: {_format_percent(float(metrics.get('spy_annualized_return', float('nan'))))}",
        f"- Strategy sharpe: {_format_float(float(metrics.get('strategy_sharpe', float('nan'))))}",
        f"- Strategy sortino: {_format_float(float(metrics.get('strategy_sortino', float('nan'))))}",
        f"- Strategy calmar: {_format_float(float(metrics.get('strategy_calmar', float('nan'))))}",
        f"- Information ratio: {_format_float(float(metrics.get('information_ratio', float('nan'))))}",
        f"- Max drawdown (strategy): {_format_percent(float(metrics.get('strategy_max_drawdown', float('nan'))))}",
        "",
        "Tail / Distribution",
        f"- Strategy VaR 95%: {_format_percent(float(metrics.get('strategy_var_95', float('nan'))))}",
        f"- Strategy CVaR 95%: {_format_percent(float(metrics.get('strategy_cvar_95', float('nan'))))}",
        "",
        "Turnover / Breadth / IC",
        f"- Avg turnover per period: {_format_float(float(metrics.get('avg_turnover_per_period', float('nan'))))}",
        f"- Avg active names: {_format_float(float(metrics.get('avg_active_names', float('nan'))), precision=2)}",
        f"- IC mean / IR / positive rate: {_format_float(float(metrics.get('ic_mean', float('nan'))))} / {_format_float(float(metrics.get('ic_ir', float('nan'))))} / {_format_percent(float(metrics.get('ic_positive_rate', float('nan'))))}",
        f"- Rank IC mean / IR / positive rate: {_format_float(float(metrics.get('rank_ic_mean', float('nan'))))} / {_format_float(float(metrics.get('rank_ic_ir', float('nan'))))} / {_format_percent(float(metrics.get('rank_ic_positive_rate', float('nan'))))}",
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
                f"- Holdout strategy total return: {_format_percent(float(hm.get('strategy_total_return', float('nan'))))}",
                f"- Holdout SPY total return: {_format_percent(float(hm.get('spy_total_return', float('nan'))))}",
                overlap_note,
                "- Holdout artifacts are exported to holdout/*.csv and holdout/metrics.json.",
            ]
        )
    return "\n".join(lines)


def write_outputs(
    *,
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
    (out_dir / "segment_a_features.txt").write_text("\n".join(segment_a.feature_columns), encoding="utf-8")
    (out_dir / "segment_b_features.txt").write_text("\n".join(segment_b.feature_columns), encoding="utf-8")
    if segment_a.selection_history is not None and not segment_a.selection_history.empty:
        segment_a.selection_history.to_csv(out_dir / "segment_a_selection_history.csv", index=False)
    if segment_b.selection_history is not None and not segment_b.selection_history.empty:
        segment_b.selection_history.to_csv(out_dir / "segment_b_selection_history.csv", index=False)


def write_holdout_outputs(*, out_dir: Path, holdout: HoldoutResult) -> None:
    holdout_dir = out_dir / "holdout"
    holdout_dir.mkdir(parents=True, exist_ok=True)
    holdout.strategy_nav.to_frame(name="strategy_nav").to_csv(holdout_dir / "strategy_nav.csv")
    holdout.spy_nav.to_frame(name="spy_nav").to_csv(holdout_dir / "spy_nav.csv")
    holdout.strategy_returns.to_frame(name="strategy_ret").to_csv(holdout_dir / "strategy_returns.csv")
    holdout.spy_returns.to_frame(name="spy_ret").to_csv(holdout_dir / "spy_returns.csv")
    holdout.strategy_turnover.to_frame(name="strategy_turnover").to_csv(holdout_dir / "strategy_turnover.csv")
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
    *,
    settings: BacktestSettings,
    segment_a_spec: SegmentSpec,
    segment_b_spec: SegmentSpec,
    holdout_result: HoldoutResult | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "resolved_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": resolve_git_commit(ROOT),
        "arguments": settings.to_display_config(),
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


def run_backtest(settings: BacktestSettings) -> dict[str, Any]:
    if settings.tuning_cv_folds < 1:
        raise ValueError("--tuning-cv-folds must be >= 1.")
    if settings.test_months < 1:
        raise ValueError("--test-months must be >= 1.")
    if settings.feature_lag_periods < 0:
        raise ValueError("--feature-lag-periods must be >= 0.")
    if settings.portfolio_qp_cov_lookback < 1:
        raise ValueError("--portfolio-qp-cov-lookback must be >= 1.")
    if settings.portfolio_qp_max_names < 0:
        raise ValueError("--portfolio-qp-max-names must be >= 0.")
    if bool(settings.holdout_start) != bool(settings.holdout_end):
        raise ValueError("Use --holdout-start and --holdout-end together.")

    model_adapter = get_model_adapter(settings.model_id)
    model_adapter.validate_configuration(
        feature_selection=settings.feature_selection,
        n_trials=settings.n_trials,
    )
    market_profile = get_market_profile(settings.market_profile)
    portfolio_cfg = build_portfolio_config(settings)

    raw = load_market_data(settings.data)
    frame = preprocess_data(
        raw,
        market_profile=market_profile,
        label_source=settings.label_source,
        label_threshold=settings.label_threshold,
        add_missing_indicators=False,
        apply_global_fill=False,
    )
    if settings.feature_lag_periods > 0:
        frame = apply_feature_lag(
            frame,
            feature_columns=get_feature_columns(frame),
            lag_periods=int(settings.feature_lag_periods),
        )

    if settings.export_parquet:
        export_frame = preprocess_data(
            raw,
            market_profile=market_profile,
            label_source=settings.label_source,
            label_threshold=settings.label_threshold,
            add_missing_indicators=settings.add_missing_indicators,
            apply_global_fill=True,
        )
        if settings.feature_lag_periods > 0:
            export_frame = apply_feature_lag(
                export_frame,
                feature_columns=get_feature_columns(export_frame),
                lag_periods=int(settings.feature_lag_periods),
            )
        save_market_data(export_frame, settings.export_parquet)

    segment_a_spec = SegmentSpec(
        name="segment_a",
        train_start="2004-01-01",
        train_end="2009-01-01",
        valid_start="2009-04-01",
        valid_end="2009-07-01",
        rolling_start=settings.segment1_start,
        rolling_windows=settings.segment1_windows,
    )
    segment_b_spec = SegmentSpec(
        name="segment_b",
        train_start="2009-01-01",
        train_end="2014-01-01",
        valid_start="2014-04-01",
        valid_end="2014-07-01",
        rolling_start=settings.segment2_start,
        rolling_windows=settings.segment2_windows,
    )

    segment_a = fit_segment_model(
        frame=frame,
        spec=segment_a_spec,
        settings=settings,
        portfolio_cfg=portfolio_cfg,
        model_adapter=model_adapter,
        market_profile=market_profile,
        seed_offset=0,
    )
    segment_b = fit_segment_model(
        frame=frame,
        spec=segment_b_spec,
        settings=settings,
        portfolio_cfg=portfolio_cfg,
        model_adapter=model_adapter,
        market_profile=market_profile,
        seed_offset=1000,
    )

    bt_a = run_rolling_backtest(
        frame=frame,
        windows=build_rolling_windows(
            start_date=segment_a_spec.rolling_start,
            n_windows=segment_a_spec.rolling_windows,
            train_months=settings.train_months,
            gap_months=settings.gap_months,
            test_months=settings.test_months,
        ),
        feature_columns=segment_a.feature_columns,
        model_params=segment_a.model_params,
        model_adapter=model_adapter,
        target_column=model_adapter.training_target_column,
        random_state=settings.random_seed,
        cost_bps=settings.cost_bps,
        initial_nav=1.0,
        add_missing_indicators=settings.add_missing_indicators,
        portfolio_config=portfolio_cfg,
        tradability_filter=market_profile.filter_tradable_frame,
    )
    bt_b = run_rolling_backtest(
        frame=frame,
        windows=build_rolling_windows(
            start_date=segment_b_spec.rolling_start,
            n_windows=segment_b_spec.rolling_windows,
            train_months=settings.train_months,
            gap_months=settings.gap_months,
            test_months=settings.test_months,
        ),
        feature_columns=segment_b.feature_columns,
        model_params=segment_b.model_params,
        model_adapter=model_adapter,
        target_column=model_adapter.training_target_column,
        random_state=settings.random_seed + 2000,
        cost_bps=settings.cost_bps,
        initial_nav=float(bt_a.nav.iloc[-1]) if not bt_a.nav.empty else 1.0,
        add_missing_indicators=settings.add_missing_indicators,
        portfolio_config=portfolio_cfg,
        tradability_filter=market_profile.filter_tradable_frame,
    )

    strategy_nav = combine_backtest_segments(bt_a.nav, bt_b.nav, name="strategy_nav")
    strategy_returns = combine_backtest_segments(bt_a.period_returns, bt_b.period_returns, name="strategy_ret")
    strategy_turnover = combine_backtest_segments(
        bt_a.period_turnover,
        bt_b.period_turnover,
        name="strategy_turnover",
    )
    active_names = combine_backtest_segments(bt_a.active_names, bt_b.active_names, name="active_names")
    period_ic = combine_backtest_segments(bt_a.period_ic, bt_b.period_ic, name="period_ic")
    period_rank_ic = combine_backtest_segments(bt_a.period_rank_ic, bt_b.period_rank_ic, name="period_rank_ic")
    spy_nav = build_spy_benchmark(frame, strategy_nav.index, benchmark_cum_col="benchmark_cum_ret")
    spy_returns = spy_nav.pct_change().dropna()
    metrics = compute_performance_metrics(
        strategy_nav,
        spy_nav,
        strategy_returns=strategy_returns,
        spy_returns=spy_returns,
        strategy_turnover=strategy_turnover,
        active_names=active_names,
        period_ic=period_ic,
        period_rank_ic=period_rank_ic,
        periods_per_year=_periods_per_year_from_test_months(settings.test_months),
    )
    holdout_result: HoldoutResult | None = None
    if settings.holdout_start and settings.holdout_end:
        holdout_segment_fit = segment_a if settings.holdout_model_segment == "segment_a" else segment_b
        holdout_result = _build_holdout_result(
            frame=frame,
            holdout_start=settings.holdout_start,
            holdout_end=settings.holdout_end,
            model_segment=settings.holdout_model_segment,
            segment_fit=holdout_segment_fit,
            settings=settings,
            portfolio_cfg=portfolio_cfg,
            model_adapter=model_adapter,
            market_profile=market_profile,
        )

    run_config = build_run_config(
        settings=settings,
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
        tuning_cv_folds=settings.tuning_cv_folds,
        holdout_result=holdout_result,
    )
    out_dir = Path(settings.output_dir)
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

    return {
        "output_dir": out_dir,
        "metrics": metrics,
        "run_summary_text": run_summary_text,
        "segment_a": segment_a,
        "segment_b": segment_b,
        "holdout_result": holdout_result,
    }


def print_run_results(results: dict[str, Any]) -> None:
    out_dir = results["output_dir"]
    segment_a = results["segment_a"]
    segment_b = results["segment_b"]
    holdout_result = results["holdout_result"]
    print(f"Output directory: {out_dir}")
    print(f"Segment A feature count: {len(segment_a.feature_columns)}")
    print(f"Segment B feature count: {len(segment_b.feature_columns)}")
    if holdout_result is not None:
        print(f"Holdout output directory: {out_dir / 'holdout'}")
    print()
    print(results["run_summary_text"])
    print()
    metrics = results["metrics"]
    if metrics:
        print(json.dumps(metrics, indent=2))
    else:
        print("No metrics were computed; verify strategy/benchmark date overlap.")


def legacy_main(argv: list[str] | None = None) -> None:
    settings = BacktestSettings.from_legacy_args(parse_legacy_args(argv))
    print_run_results(run_backtest(settings))
