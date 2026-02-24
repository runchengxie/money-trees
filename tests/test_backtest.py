from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.backtest import (
    build_rolling_windows,
    compute_performance_metrics,
    run_rolling_backtest,
)
from strategy.data import preprocess_data


def test_build_rolling_windows_shape_and_dates() -> None:
    windows = build_rolling_windows(
        start_date="2020-01-01",
        n_windows=2,
        train_months=12,
        gap_months=3,
        test_months=3,
    )
    assert len(windows) == 2
    assert windows[0] == ("2020-01-01", "2021-01-01", "2021-04-01", "2021-07-01")
    assert windows[1] == ("2020-04-01", "2021-04-01", "2021-07-01", "2021-10-01")


def test_compute_performance_metrics_uses_return_rates_not_nav_diff() -> None:
    idx = pd.to_datetime(["2021-03-31", "2021-06-30", "2021-09-30"])
    strategy_nav = pd.Series([1.0, 2.0, 2.2], index=idx)
    spy_nav = pd.Series([1.0, 1.5, 1.65], index=idx)

    metrics = compute_performance_metrics(strategy_nav, spy_nav)

    expected_strategy_ret = strategy_nav.pct_change().dropna()
    expected_sharpe = expected_strategy_ret.mean() / expected_strategy_ret.std()
    assert np.isclose(metrics["strategy_sharpe"], expected_sharpe)


def test_run_rolling_backtest_outputs_stable_series() -> None:
    dates = pd.date_range("2020-01-31", periods=18, freq="ME")
    tickers = ["A", "B", "C"]
    rows: list[dict[str, object]] = []

    for d in dates:
        for i, t in enumerate(tickers):
            signal = (i - 1) * 0.5
            rows.append(
                {
                    "date": d,
                    "ticker": t,
                    "f1": signal,
                    "f2": float(i),
                    "next_period_return": 0.01 + 0.02 * signal,
                    "spy_next_period_return": 0.005,
                    "spy_cum_ret": 1.0 + 0.001 * len(rows),
                }
            )

    raw = pd.DataFrame(rows)
    frame = preprocess_data(raw, apply_global_fill=False)
    windows = [
        ("2020-01-01", "2020-10-31", "2020-11-01", "2021-01-31"),
        ("2020-04-01", "2021-01-31", "2021-02-01", "2021-04-30"),
    ]

    result = run_rolling_backtest(
        frame=frame,
        windows=windows,
        feature_columns=["f1", "f2"],
        model_params={
            "n_estimators": 20,
            "max_depth": 6,
            "min_samples_leaf": 1,
            "max_features": "sqrt",
        },
        random_state=3,
        cost_bps=10.0,
    )

    assert len(result.nav) == len(result.period_returns)
    assert len(result.nav) > 0
    assert not result.nav.isna().any()
    assert not result.period_returns.isna().any()
