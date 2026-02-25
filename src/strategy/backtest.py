from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import linregress

from .data import build_spy_series, build_xy_returns, fill_missing_with_reference, slice_by_date
from .model import fit_random_forest
from .portfolio import (
    PortfolioConfig,
    build_portfolio_weights,
    build_signal_scores,
    compute_period_return_from_weights,
)


@dataclass
class BacktestResult:
    nav: pd.Series
    period_returns: pd.Series
    period_turnover: pd.Series
    active_names: pd.Series
    period_ic: pd.Series
    period_rank_ic: pd.Series


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


def _safe_corr(signal: pd.Series, target: pd.Series, method: str = "pearson") -> float:
    aligned = pd.concat([signal.rename("signal"), target.rename("target")], axis=1).dropna()
    if len(aligned) < 2:
        return float("nan")
    if aligned["signal"].nunique() < 2 or aligned["target"].nunique() < 2:
        return float("nan")
    value = aligned["signal"].corr(aligned["target"], method=method)
    return float(value) if pd.notna(value) else float("nan")


def _compute_period_ic(
    predictions: np.ndarray,
    realized_returns: np.ndarray,
    sample_index: pd.Index,
) -> tuple[float, float]:
    signal = pd.Series(predictions, index=sample_index, dtype=float)
    realized = pd.Series(realized_returns, index=sample_index, dtype=float)

    if isinstance(sample_index, pd.MultiIndex) and "date" in sample_index.names:
        paired = pd.concat([signal.rename("signal"), realized.rename("realized")], axis=1).dropna()
        if paired.empty:
            return float("nan"), float("nan")

        pearson_values: list[float] = []
        spearman_values: list[float] = []
        for _, group in paired.groupby(level="date", sort=False):
            pearson = _safe_corr(group["signal"], group["realized"], method="pearson")
            spearman = _safe_corr(group["signal"], group["realized"], method="spearman")
            if not np.isnan(pearson):
                pearson_values.append(float(pearson))
            if not np.isnan(spearman):
                spearman_values.append(float(spearman))

        period_ic = float(np.mean(pearson_values)) if pearson_values else float("nan")
        period_rank_ic = float(np.mean(spearman_values)) if spearman_values else float("nan")
        return period_ic, period_rank_ic

    period_ic = _safe_corr(signal, realized, method="pearson")
    period_rank_ic = _safe_corr(signal, realized, method="spearman")
    return period_ic, period_rank_ic


def _max_drawdown(nav: pd.Series) -> float:
    if nav.empty:
        return float("nan")
    drawdown = nav / nav.cummax() - 1.0
    return float(drawdown.min())


def run_rolling_backtest(
    frame: pd.DataFrame,
    windows: list[tuple[str, str, str, str]],
    feature_columns: list[str],
    model_params: dict[str, object],
    random_state: int = 123,
    cost_bps: float = 0.0,
    initial_nav: float = 1.0,
    add_missing_indicators: bool = False,
    portfolio_config: PortfolioConfig | None = None,
) -> BacktestResult:
    portfolio_cfg = PortfolioConfig() if portfolio_config is None else portfolio_config
    nav_value = float(initial_nav)
    nav_points: list[float] = []
    period_returns: list[float] = []
    period_turnovers: list[float] = []
    active_names: list[int] = []
    period_ic_values: list[float] = []
    period_rank_ic_values: list[float] = []
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
        probs: np.ndarray | None = None
        classes_: np.ndarray | None = None
        if portfolio_cfg.use_prob_signal and hasattr(model, "predict_proba"):
            probs = model.predict_proba(test_x)
            classes_ = getattr(model, "classes_", None)

        signal_scores = build_signal_scores(
            predictions=preds,
            probs=probs,
            classes_=classes_,
            use_prob_signal=portfolio_cfg.use_prob_signal,
        )
        current_weights = build_portfolio_weights(
            predictions=preds,
            probs=probs,
            classes_=classes_,
            sample_index=test_x.index,
            train_frame=train_frame,
            test_frame=test_frame,
            cfg=portfolio_cfg,
            previous_weights=previous_weights,
        )
        period_return, current_weights, turnover = compute_period_return_from_weights(
            weights=current_weights,
            realized_returns=test_returns,
            sample_index=test_x.index,
            cost_bps=cost_bps,
            previous_weights=previous_weights,
        )
        previous_weights = current_weights
        period_ic, period_rank_ic = _compute_period_ic(
            predictions=signal_scores,
            realized_returns=test_returns,
            sample_index=test_x.index,
        )

        nav_value *= 1.0 + period_return
        nav_points.append(nav_value)
        period_returns.append(period_return)
        period_turnovers.append(turnover)
        active_names.append(int(len(current_weights)))
        period_ic_values.append(period_ic)
        period_rank_ic_values.append(period_rank_ic)
        period_dates.append(_resolve_period_date(test_frame, fallback=test_end))

    nav = pd.Series(nav_points, index=period_dates, name="strategy_nav")
    returns = pd.Series(period_returns, index=period_dates, name="strategy_ret")
    turnover = pd.Series(period_turnovers, index=period_dates, name="strategy_turnover")
    active = pd.Series(active_names, index=period_dates, name="active_names")
    period_ic = pd.Series(period_ic_values, index=period_dates, name="period_ic")
    period_rank_ic = pd.Series(period_rank_ic_values, index=period_dates, name="period_rank_ic")
    return BacktestResult(
        nav=nav,
        period_returns=returns,
        period_turnover=turnover,
        active_names=active,
        period_ic=period_ic,
        period_rank_ic=period_rank_ic,
    )


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
    strategy_turnover: pd.Series | None = None,
    active_names: pd.Series | None = None,
    period_ic: pd.Series | None = None,
    period_rank_ic: pd.Series | None = None,
    periods_per_year: float = 4.0,
    var_confidence: float = 0.95,
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
    strategy_start_nav = float(aligned_nav["strategy_nav"].iloc[0])
    strategy_end_nav = float(aligned_nav["strategy_nav"].iloc[-1])
    spy_start_nav = float(aligned_nav["spy_nav"].iloc[0])
    spy_end_nav = float(aligned_nav["spy_nav"].iloc[-1])
    strategy_total_return = (
        float(strategy_end_nav / strategy_start_nav - 1.0)
        if np.isfinite(strategy_start_nav) and strategy_start_nav != 0
        else float("nan")
    )
    spy_total_return = (
        float(spy_end_nav / spy_start_nav - 1.0)
        if np.isfinite(spy_start_nav) and spy_start_nav != 0
        else float("nan")
    )

    n_nav_periods = len(aligned_nav) - 1
    strategy_ann_return = (
        float((strategy_end_nav / strategy_start_nav) ** (periods_per_year / n_nav_periods) - 1.0)
        if n_nav_periods > 0
        else float("nan")
    )
    spy_ann_return = (
        float((spy_end_nav / spy_start_nav) ** (periods_per_year / n_nav_periods) - 1.0)
        if n_nav_periods > 0
        else float("nan")
    )
    strategy_ann_vol = (
        float(strategy_ret.std(ddof=1) * np.sqrt(periods_per_year))
        if len(strategy_ret) > 1
        else float("nan")
    )
    spy_ann_vol = (
        float(spy_ret.std(ddof=1) * np.sqrt(periods_per_year))
        if len(spy_ret) > 1
        else float("nan")
    )

    strategy_mdd = _max_drawdown(aligned_nav["strategy_nav"])
    spy_mdd = _max_drawdown(aligned_nav["spy_nav"])

    downside = np.minimum(strategy_ret.to_numpy(), 0.0)
    strategy_downside_vol = (
        float(np.sqrt(np.mean(np.square(downside))) * np.sqrt(periods_per_year))
        if len(downside) > 0
        else float("nan")
    )
    strategy_sortino = (
        float(strategy_ret.mean() * periods_per_year / strategy_downside_vol)
        if np.isfinite(strategy_downside_vol) and strategy_downside_vol > 0
        else float("nan")
    )
    strategy_calmar = (
        float(strategy_ann_return / abs(strategy_mdd))
        if np.isfinite(strategy_mdd) and strategy_mdd < 0 and np.isfinite(strategy_ann_return)
        else float("nan")
    )

    var_level = 1.0 - var_confidence
    strategy_var = float(strategy_ret.quantile(var_level))
    strategy_tail = strategy_ret[strategy_ret <= strategy_var]
    strategy_cvar = float(strategy_tail.mean()) if not strategy_tail.empty else float("nan")
    spy_var = float(spy_ret.quantile(var_level))
    spy_tail = spy_ret[spy_ret <= spy_var]
    spy_cvar = float(spy_tail.mean()) if not spy_tail.empty else float("nan")

    excess_ret = strategy_ret - spy_ret
    win_rate_vs_spy = float((excess_ret > 0).mean())
    avg_excess_return = float(excess_ret.mean())
    tracking_error = (
        float(excess_ret.std(ddof=1) * np.sqrt(periods_per_year))
        if len(excess_ret) > 1
        else float("nan")
    )
    info_ratio = (
        float(avg_excess_return * periods_per_year / tracking_error)
        if np.isfinite(tracking_error) and tracking_error != 0
        else float("nan")
    )

    alpha = float("nan")
    beta = float("nan")
    hedged_sharpe = float("nan")
    if len(strategy_ret) >= 2 and len(spy_ret) >= 2:
        reg = linregress(spy_ret.to_numpy(), strategy_ret.to_numpy())
        beta = float(reg.slope)
        alpha = float(reg.intercept)

        hedged_ret = strategy_ret - beta * spy_ret
        hedged_std = float(hedged_ret.std()) if not hedged_ret.empty else 0.0
        hedged_sharpe = (
            float(hedged_ret.mean() / hedged_std)
            if np.isfinite(hedged_std) and hedged_std != 0
            else 0.0
        )
    metrics: dict[str, float] = {
        "strategy_total_return": strategy_total_return,
        "spy_total_return": spy_total_return,
        "strategy_annualized_return": strategy_ann_return,
        "spy_annualized_return": spy_ann_return,
        "strategy_annualized_volatility": strategy_ann_vol,
        "spy_annualized_volatility": spy_ann_vol,
        "strategy_max_drawdown": strategy_mdd,
        "spy_max_drawdown": spy_mdd,
        "strategy_sharpe": strategy_sharpe,
        "spy_sharpe": spy_sharpe,
        "strategy_sortino": strategy_sortino,
        "strategy_calmar": strategy_calmar,
        "strategy_skew": float(strategy_ret.skew()),
        "strategy_kurtosis": float(strategy_ret.kurt()),
        "spy_skew": float(spy_ret.skew()),
        "spy_kurtosis": float(spy_ret.kurt()),
        "strategy_var_95": strategy_var,
        "strategy_cvar_95": strategy_cvar,
        "spy_var_95": spy_var,
        "spy_cvar_95": spy_cvar,
        "win_rate_vs_spy": win_rate_vs_spy,
        "avg_excess_return_per_period": avg_excess_return,
        "tracking_error_annualized": tracking_error,
        "alpha": alpha,
        "beta": beta,
        "information_ratio": info_ratio,
        "hedged_sharpe": hedged_sharpe,
    }

    if strategy_turnover is not None:
        turnover = strategy_turnover.dropna()
        metrics["avg_turnover_per_period"] = float(turnover.mean()) if not turnover.empty else float(
            "nan"
        )
        metrics["median_turnover_per_period"] = (
            float(turnover.median()) if not turnover.empty else float("nan")
        )
        metrics["max_turnover_per_period"] = float(turnover.max()) if not turnover.empty else float(
            "nan"
        )
        metrics["annualized_turnover"] = (
            float(turnover.mean() * periods_per_year) if not turnover.empty else float("nan")
        )

    if active_names is not None:
        active = active_names.dropna()
        metrics["avg_active_names"] = float(active.mean()) if not active.empty else float("nan")
        metrics["median_active_names"] = float(active.median()) if not active.empty else float("nan")
        metrics["min_active_names"] = float(active.min()) if not active.empty else float("nan")
        metrics["max_active_names"] = float(active.max()) if not active.empty else float("nan")

    if period_ic is not None:
        ic = period_ic.dropna()
        ic_std = float(ic.std(ddof=1)) if len(ic) > 1 else float("nan")
        metrics["ic_mean"] = float(ic.mean()) if not ic.empty else float("nan")
        metrics["ic_std"] = ic_std
        metrics["ic_ir"] = (
            float(ic.mean() / ic_std) if np.isfinite(ic_std) and ic_std != 0 else float("nan")
        )
        metrics["ic_positive_rate"] = float((ic > 0).mean()) if not ic.empty else float("nan")

    if period_rank_ic is not None:
        rank_ic = period_rank_ic.dropna()
        rank_ic_std = float(rank_ic.std(ddof=1)) if len(rank_ic) > 1 else float("nan")
        metrics["rank_ic_mean"] = float(rank_ic.mean()) if not rank_ic.empty else float("nan")
        metrics["rank_ic_std"] = rank_ic_std
        metrics["rank_ic_ir"] = (
            float(rank_ic.mean() / rank_ic_std)
            if np.isfinite(rank_ic_std) and rank_ic_std != 0
            else float("nan")
        )
        metrics["rank_ic_positive_rate"] = (
            float((rank_ic > 0).mean()) if not rank_ic.empty else float("nan")
        )

    return metrics
