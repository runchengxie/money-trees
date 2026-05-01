from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from moneytree.backtest import build_benchmark_nav, compute_performance_metrics
from moneytree.config import BacktestSettings
from moneytree.data import (
    apply_missing_feature_policy,
    build_xy_target_returns,
    fill_feature_missing_with_reference,
    slice_by_date,
)
from moneytree.model import count_active_names, profit_with_estimated_turnover
from moneytree.portfolio import (
    PortfolioConfig,
    build_portfolio_weights,
    compute_period_return_from_weights,
)


@dataclass
class HoldoutResult:
    model_segment: str
    train_start: str
    train_end: str
    holdout_start: str
    holdout_end: str
    benchmark_name: str
    strategy_nav: pd.Series
    benchmark_nav: pd.Series
    strategy_returns: pd.Series
    benchmark_returns: pd.Series
    strategy_turnover: pd.Series
    active_names: pd.Series
    signal_nav: pd.Series
    signal_profit: pd.Series
    signal_turnover: pd.Series
    signal_active_names: pd.Series
    period_ic: pd.Series
    period_rank_ic: pd.Series
    portfolio_diagnostics: pd.DataFrame
    model_segment_train_start: str
    model_segment_train_end: str
    model_segment_valid_start: str
    model_segment_valid_end: str
    metrics: dict[str, float]


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
    segment_fit: Any,
    settings: BacktestSettings,
    portfolio_cfg: PortfolioConfig,
    model_adapter: Any,
    market_profile: Any,
) -> HoldoutResult:
    holdout_start_ts = pd.Timestamp(holdout_start)
    holdout_end_ts = pd.Timestamp(holdout_end)
    if holdout_start_ts > holdout_end_ts:
        raise ValueError("--holdout-start must be <= --holdout-end.")

    date_values = pd.Index(frame.index.get_level_values("date"))
    train_raw = market_profile.filter_tradable_frame(
        frame.loc[date_values < holdout_start_ts],
        settings=settings,
    )
    holdout_raw = market_profile.filter_tradable_frame(
        slice_by_date(frame, holdout_start, holdout_end),
        settings=settings,
    )
    if train_raw.empty or holdout_raw.empty:
        raise ValueError("Holdout train/test frame is empty; adjust holdout dates.")

    train_frame = fill_feature_missing_with_reference(
        frame=train_raw,
        reference=train_raw,
        add_missing_indicators=settings.add_missing_indicators,
    )
    holdout_frame = fill_feature_missing_with_reference(
        frame=holdout_raw,
        reference=train_raw,
        add_missing_indicators=settings.add_missing_indicators,
    )
    feature_columns = list(segment_fit.feature_columns)
    train_frame = apply_missing_feature_policy(
        train_frame,
        feature_columns,
        frame_role="holdout train frame",
        policy=settings.missing_feature_policy,
    )
    holdout_frame = apply_missing_feature_policy(
        holdout_frame,
        feature_columns,
        frame_role="holdout frame",
        policy=settings.missing_feature_policy,
    )

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
        outputs.predictions
        if outputs.predictions is not None
        else np.zeros(len(holdout_x), dtype=int)
    )
    holdout_probabilities = outputs.probabilities
    holdout_scores = outputs.scores

    period_dates: list[pd.Timestamp] = []
    period_returns: list[float] = []
    period_turnover: list[float] = []
    period_active_names: list[int] = []
    signal_period_profits: list[float] = []
    signal_turnovers: list[float] = []
    signal_active_name_counts: list[int] = []
    period_ic_values: list[float] = []
    period_rank_ic_values: list[float] = []
    portfolio_diagnostic_rows: list[dict[str, float | bool]] = []
    nav_points: list[float] = []
    nav_value = 1.0
    signal_nav_points: list[float] = []
    signal_nav_value = 1.0
    previous_weights: pd.Series | None = None
    previous_signal_weights: pd.Series | None = None
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
        signal_profit, signal_weights, signal_turnover = profit_with_estimated_turnover(
            predictions=np.asarray(holdout_predictions[mask], dtype=int),
            realized_returns=holdout_returns[mask],
            cost_bps=settings.cost_bps,
            sample_index=idx,
            previous_weights=previous_signal_weights,
        )
        previous_weights = current_weights
        previous_signal_weights = signal_weights
        ic_value, rank_ic_value = _period_ic(
            predictions=holdout_scores[mask],
            realized_returns=holdout_returns[mask],
            sample_index=idx,
        )
        nav_value *= 1.0 + period_profit
        signal_nav_value *= 1.0 + signal_profit
        target_gross = max(float(portfolio_cfg.gross_target), 0.0)
        realized_gross = float(current_weights.abs().sum()) if not current_weights.empty else 0.0
        period_diagnostics = {
            "target_gross": target_gross,
            "realized_gross": realized_gross,
            "target_net": float(
                np.clip(
                    portfolio_cfg.net_target,
                    -portfolio_cfg.gross_target,
                    portfolio_cfg.gross_target,
                )
            ),
            "realized_net": float(current_weights.sum()) if not current_weights.empty else 0.0,
            "unallocated_exposure": max(0.0, target_gross - realized_gross),
            "qp_fallback": bool(current_weights.attrs.get("qp_fallback", False)),
        }
        nav_points.append(nav_value)
        signal_nav_points.append(signal_nav_value)
        period_dates.append(_resolve_period_date_from_index(idx, fallback=period_end))
        period_returns.append(float(period_profit))
        period_turnover.append(float(turnover))
        period_active_names.append(int(len(current_weights)))
        signal_period_profits.append(float(signal_profit))
        signal_turnovers.append(float(signal_turnover))
        signal_active_name_counts.append(
            count_active_names(np.asarray(holdout_predictions[mask], dtype=int), idx)
        )
        period_ic_values.append(float(ic_value))
        period_rank_ic_values.append(float(rank_ic_value))
        portfolio_diagnostic_rows.append(period_diagnostics)

    strategy_nav = pd.Series(nav_points, index=period_dates, name="strategy_nav")
    signal_nav = pd.Series(signal_nav_points, index=period_dates, name="signal_nav")
    strategy_returns = pd.Series(period_returns, index=period_dates, name="strategy_ret")
    signal_profit_series = pd.Series(
        signal_period_profits,
        index=period_dates,
        name="signal_profit",
    )
    strategy_turnover = pd.Series(period_turnover, index=period_dates, name="strategy_turnover")
    signal_turnover_series = pd.Series(
        signal_turnovers,
        index=period_dates,
        name="signal_turnover",
    )
    active_names = pd.Series(period_active_names, index=period_dates, name="active_names")
    signal_active_names = pd.Series(
        signal_active_name_counts,
        index=period_dates,
        name="signal_active_names",
    )
    period_ic_series = pd.Series(period_ic_values, index=period_dates, name="period_ic")
    period_rank_ic_series = pd.Series(
        period_rank_ic_values,
        index=period_dates,
        name="period_rank_ic",
    )
    portfolio_diagnostics = pd.DataFrame(portfolio_diagnostic_rows, index=period_dates)
    if not portfolio_diagnostics.empty:
        portfolio_diagnostics.index.name = "date"
    benchmark_nav = build_benchmark_nav(
        frame,
        strategy_nav.index,
        benchmark_cum_col="benchmark_cum_ret",
        benchmark_cum_mode=settings.benchmark_cum_mode,
    )
    benchmark_returns = benchmark_nav.pct_change().dropna()
    metrics = compute_performance_metrics(
        strategy_nav=strategy_nav,
        benchmark_nav=benchmark_nav,
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        strategy_turnover=strategy_turnover,
        active_names=active_names,
        period_ic=period_ic_series,
        period_rank_ic=period_rank_ic_series,
        periods_per_year=_periods_per_year_from_test_months(settings.test_months),
    )
    return HoldoutResult(
        model_segment=model_segment,
        train_start=pd.Timestamp(train_raw.index.get_level_values("date").min()).strftime(
            "%Y-%m-%d"
        ),
        train_end=pd.Timestamp(train_raw.index.get_level_values("date").max()).strftime(
            "%Y-%m-%d"
        ),
        holdout_start=holdout_start_ts.strftime("%Y-%m-%d"),
        holdout_end=holdout_end_ts.strftime("%Y-%m-%d"),
        benchmark_name=settings.benchmark_name,
        strategy_nav=strategy_nav,
        benchmark_nav=benchmark_nav,
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        strategy_turnover=strategy_turnover,
        active_names=active_names,
        signal_nav=signal_nav,
        signal_profit=signal_profit_series,
        signal_turnover=signal_turnover_series,
        signal_active_names=signal_active_names,
        period_ic=period_ic_series,
        period_rank_ic=period_rank_ic_series,
        portfolio_diagnostics=portfolio_diagnostics,
        model_segment_train_start=segment_fit.train_start,
        model_segment_train_end=segment_fit.train_end,
        model_segment_valid_start=segment_fit.valid_start,
        model_segment_valid_end=segment_fit.valid_end,
        metrics=metrics,
    )
