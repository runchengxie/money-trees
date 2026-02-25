from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.backtest import (
    build_rolling_windows,
    build_spy_benchmark,
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
    assert "strategy_annualized_return" in metrics
    assert "strategy_max_drawdown" in metrics
    assert "strategy_var_95" in metrics


def test_compute_performance_metrics_information_ratio_uses_excess_tracking_error() -> None:
    idx = pd.to_datetime(["2021-03-31", "2021-06-30", "2021-09-30", "2021-12-31"])
    strategy_ret = pd.Series([0.08, -0.02, 0.03, 0.04], index=idx)
    spy_ret = pd.Series([0.03, -0.01, 0.01, 0.02], index=idx)
    strategy_nav = (1.0 + strategy_ret).cumprod()
    spy_nav = (1.0 + spy_ret).cumprod()

    metrics = compute_performance_metrics(
        strategy_nav=strategy_nav,
        spy_nav=spy_nav,
        strategy_returns=strategy_ret,
        spy_returns=spy_ret,
        periods_per_year=4.0,
    )

    excess = strategy_ret - spy_ret
    expected_tracking_error = float(excess.std(ddof=1) * np.sqrt(4.0))
    expected_ir = float(excess.mean() * 4.0 / expected_tracking_error)
    assert np.isclose(metrics["tracking_error_annualized"], expected_tracking_error)
    assert np.isclose(metrics["information_ratio"], expected_ir)


def test_compute_performance_metrics_total_return_is_interval_consistent() -> None:
    idx = pd.to_datetime(["2021-03-31", "2021-06-30", "2021-09-30"])
    strategy_nav = pd.Series([1.10, 1.21, 1.331], index=idx)
    spy_nav = pd.Series([1.00, 1.02, 1.03], index=idx)

    metrics = compute_performance_metrics(
        strategy_nav=strategy_nav,
        spy_nav=spy_nav,
        periods_per_year=4.0,
    )

    expected_total = float(strategy_nav.iloc[-1] / strategy_nav.iloc[0] - 1.0)
    expected_ann = float((1.0 + expected_total) ** (4.0 / (len(idx) - 1)) - 1.0)
    assert np.isclose(metrics["strategy_total_return"], expected_total)
    assert np.isclose(metrics["strategy_annualized_return"], expected_ann)


def test_compute_performance_metrics_returns_empty_when_nav_has_no_overlap() -> None:
    strategy_nav = pd.Series(
        [1.0, 1.1],
        index=pd.to_datetime(["2021-03-31", "2021-06-30"]),
    )
    spy_nav = pd.Series(
        [1.0, 1.1],
        index=pd.to_datetime(["2022-03-31", "2022-06-30"]),
    )

    metrics = compute_performance_metrics(strategy_nav=strategy_nav, spy_nav=spy_nav)

    assert metrics == {}


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
    assert len(result.nav) == len(result.period_turnover)
    assert len(result.nav) == len(result.active_names)
    assert len(result.nav) == len(result.period_ic)
    assert len(result.nav) == len(result.period_rank_ic)
    assert len(result.nav) > 0
    assert not result.nav.isna().any()
    assert not result.period_returns.isna().any()
    assert not result.period_turnover.isna().any()


def test_build_spy_benchmark_aligns_and_rebases_target_index() -> None:
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-03-31"), "B"),
            (pd.Timestamp("2021-06-30"), "A"),
            (pd.Timestamp("2021-06-30"), "B"),
            (pd.Timestamp("2021-09-30"), "A"),
            (pd.Timestamp("2021-09-30"), "B"),
        ],
        names=["date", "ticker"],
    )
    frame = pd.DataFrame({"spy_cum_ret": [100.0, 100.0, 110.0, 110.0, 121.0, 121.0]}, index=idx)
    target_index = pd.to_datetime(["2021-06-30", "2021-09-30"])

    spy_nav = build_spy_benchmark(frame=frame, target_index=target_index)

    assert spy_nav.index.equals(target_index)
    assert np.isclose(float(spy_nav.iloc[0]), 1.0)
    assert float(spy_nav.iloc[1]) > float(spy_nav.iloc[0])
