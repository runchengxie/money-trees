from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import linregress

from .data import build_spy_series, build_xy_returns, fill_missing_with_reference, slice_by_date
from .model import (
    count_active_names,
    estimate_turnover,
    fit_random_forest,
    predictions_to_name_weights,
    signal_profit,
)


@dataclass
class BacktestResult:
    nav: pd.Series
    period_returns: pd.Series
    active_names: pd.Series


def build_rolling_windows(
    start_date: str,
    n_windows: int,
    train_months: int = 60,
    gap_months: int = 3,
    test_months: int = 3,
) -> list[tuple[str, str, str, str]]:
    windows: list[tuple[str, str, str, str]] = []
    start = pd.Timestamp(start_date)

    for i in range(n_windows):
        train_start = start + pd.DateOffset(months=3 * i)
        train_end = train_start + pd.DateOffset(months=train_months)
        test_start = train_end + pd.DateOffset(months=gap_months)
        test_end = test_start + pd.DateOffset(months=test_months)
        windows.append(
            (
                train_start.strftime("%Y-%m-%d"),
                train_end.strftime("%Y-%m-%d"),
                test_start.strftime("%Y-%m-%d"),
                test_end.strftime("%Y-%m-%d"),
            )
        )
    return windows


def _resolve_period_date(test_frame: pd.DataFrame, fallback: str) -> pd.Timestamp:
    if isinstance(test_frame.index, pd.MultiIndex) and "date" in test_frame.index.names:
        last_date = test_frame.index.get_level_values("date").max()
        if pd.notna(last_date):
            return pd.Timestamp(last_date)
    return pd.Timestamp(fallback)


def run_rolling_backtest(
    frame: pd.DataFrame,
    windows: list[tuple[str, str, str, str]],
    feature_columns: list[str],
    model_params: dict[str, object],
    random_state: int = 123,
    cost_bps: float = 0.0,
    initial_nav: float = 1.0,
    add_missing_indicators: bool = False,
) -> BacktestResult:
    nav_value = float(initial_nav)
    nav_points: list[float] = []
    period_returns: list[float] = []
    active_names: list[int] = []
    period_dates: list[pd.Timestamp] = []
    previous_weights: pd.Series | None = None

    for idx, (train_start, train_end, test_start, test_end) in enumerate(windows):
        train_raw = slice_by_date(frame, train_start, train_end)
        test_raw = slice_by_date(frame, test_start, test_end)
        if train_raw.empty or test_raw.empty:
            continue

        train_frame = fill_missing_with_reference(
            frame=train_raw,
            reference=train_raw,
            add_missing_indicators=add_missing_indicators,
        )
        test_frame = fill_missing_with_reference(
            frame=test_raw,
            reference=train_raw,
            add_missing_indicators=add_missing_indicators,
        )
        for col in feature_columns:
            if col not in train_frame.columns:
                train_frame[col] = 0.0
            if col not in test_frame.columns:
                test_frame[col] = 0.0

        train_x, train_y, _ = build_xy_returns(train_frame, feature_columns)
        test_x, _, test_returns = build_xy_returns(test_frame, feature_columns)
        if train_x.empty or test_x.empty:
            continue

        model = fit_random_forest(
            train_x=train_x,
            train_y=train_y,
            params=model_params,
            random_state=random_state + idx,
        )
        preds = model.predict(test_x)
        current_weights = predictions_to_name_weights(preds, sample_index=test_x.index)
        turnover = estimate_turnover(current_weights, previous_weights=previous_weights)
        period_return = signal_profit(preds, test_returns, cost_bps=cost_bps, turnover=turnover)
        previous_weights = current_weights

        nav_value *= 1.0 + period_return
        nav_points.append(nav_value)
        period_returns.append(period_return)
        active_names.append(count_active_names(preds, sample_index=test_x.index))
        period_dates.append(_resolve_period_date(test_frame, fallback=test_end))

    nav = pd.Series(nav_points, index=period_dates, name="strategy_nav")
    returns = pd.Series(period_returns, index=period_dates, name="strategy_ret")
    active = pd.Series(active_names, index=period_dates, name="active_names")
    return BacktestResult(nav=nav, period_returns=returns, active_names=active)


def build_spy_benchmark(
    frame: pd.DataFrame,
    target_index: pd.Index,
    frequency: str = "QE",
) -> pd.Series:
    spy = build_spy_series(frame).resample(frequency).ffill()
    if spy.empty:
        return pd.Series(dtype=float, name="spy_nav")

    spy_nav = spy - float(spy.iloc[0]) + 1.0
    aligned = spy_nav.reindex(target_index, method="ffill")
    if not aligned.empty:
        aligned = aligned - float(aligned.iloc[0]) + 1.0
    aligned.name = "spy_nav"
    return aligned


def compute_performance_metrics(
    strategy_nav: pd.Series,
    spy_nav: pd.Series,
    strategy_returns: pd.Series | None = None,
    spy_returns: pd.Series | None = None,
) -> dict[str, float]:
    if strategy_nav.empty:
        return {}

    aligned_nav = pd.concat([strategy_nav, spy_nav], axis=1).dropna()
    aligned_nav.columns = ["strategy_nav", "spy_nav"]
    if aligned_nav.empty:
        return {}

    if strategy_returns is None:
        strategy_ret = aligned_nav["strategy_nav"].pct_change()
    else:
        strategy_ret = strategy_returns.copy()
    if spy_returns is None:
        spy_ret = aligned_nav["spy_nav"].pct_change()
    else:
        spy_ret = spy_returns.copy()

    aligned_ret = pd.concat([strategy_ret, spy_ret], axis=1).dropna()
    aligned_ret.columns = ["strategy_ret", "spy_ret"]
    if aligned_ret.empty:
        return {}

    strategy_ret = aligned_ret["strategy_ret"]
    spy_ret = aligned_ret["spy_ret"]
    strategy_std = float(strategy_ret.std())
    spy_std = float(spy_ret.std())
    strategy_sharpe = (
        float(strategy_ret.mean() / strategy_std)
        if np.isfinite(strategy_std) and strategy_std != 0
        else 0.0
    )
    spy_sharpe = (
        float(spy_ret.mean() / spy_std)
        if np.isfinite(spy_std) and spy_std != 0
        else 0.0
    )

    if len(strategy_ret) < 2 or len(spy_ret) < 2:
        return {
            "strategy_total_return": float(aligned_nav["strategy_nav"].iloc[-1] - 1.0),
            "spy_total_return": float(aligned_nav["spy_nav"].iloc[-1] - 1.0),
            "strategy_sharpe": strategy_sharpe,
            "spy_sharpe": spy_sharpe,
            "alpha": float("nan"),
            "beta": float("nan"),
            "information_ratio": float("nan"),
            "hedged_sharpe": float("nan"),
        }

    reg = linregress(spy_ret.to_numpy(), strategy_ret.to_numpy())
    beta = float(reg.slope)
    alpha = float(reg.intercept)
    residual = strategy_ret.to_numpy() - (alpha + beta * spy_ret.to_numpy())
    residual_std = float(np.std(residual, ddof=1))
    info_ratio = float(np.mean(residual) / residual_std) if residual_std != 0 else 0.0

    hedged_ret = strategy_ret - beta * spy_ret
    hedged_std = float(hedged_ret.std()) if not hedged_ret.empty else 0.0
    hedged_sharpe = (
        float(hedged_ret.mean() / hedged_std)
        if np.isfinite(hedged_std) and hedged_std != 0
        else 0.0
    )

    return {
        "strategy_total_return": float(aligned_nav["strategy_nav"].iloc[-1] - 1.0),
        "spy_total_return": float(aligned_nav["spy_nav"].iloc[-1] - 1.0),
        "strategy_sharpe": strategy_sharpe,
        "spy_sharpe": spy_sharpe,
        "alpha": alpha,
        "beta": beta,
        "information_ratio": info_ratio,
        "hedged_sharpe": hedged_sharpe,
    }
