from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from moneytree.backtest import (
    build_benchmark_nav,
    build_notebook_report_artifacts,
    build_rolling_windows,
    compute_performance_metrics,
    run_rolling_backtest,
)
from moneytree.config import BacktestSettings
from moneytree.data import preprocess_data
from moneytree.markets import get_market_profile
from moneytree.runner import SegmentFitResult, _build_holdout_result, build_portfolio_config


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
    benchmark_nav = pd.Series([1.0, 1.5, 1.65], index=idx)

    metrics = compute_performance_metrics(strategy_nav, benchmark_nav)

    expected_strategy_ret = strategy_nav.pct_change().dropna()
    expected_sharpe = expected_strategy_ret.mean() / expected_strategy_ret.std()
    assert np.isclose(metrics["strategy_sharpe"], expected_sharpe)
    assert "strategy_annualized_return" in metrics
    assert "strategy_max_drawdown" in metrics
    assert "strategy_var_95" in metrics


def test_compute_performance_metrics_information_ratio_uses_excess_tracking_error() -> None:
    idx = pd.to_datetime(["2021-03-31", "2021-06-30", "2021-09-30", "2021-12-31"])
    strategy_ret = pd.Series([0.08, -0.02, 0.03, 0.04], index=idx)
    benchmark_ret = pd.Series([0.03, -0.01, 0.01, 0.02], index=idx)
    strategy_nav = (1.0 + strategy_ret).cumprod()
    benchmark_nav = (1.0 + benchmark_ret).cumprod()

    metrics = compute_performance_metrics(
        strategy_nav=strategy_nav,
        benchmark_nav=benchmark_nav,
        strategy_returns=strategy_ret,
        benchmark_returns=benchmark_ret,
        periods_per_year=4.0,
    )

    excess = strategy_ret - benchmark_ret
    expected_tracking_error = float(excess.std(ddof=1) * np.sqrt(4.0))
    expected_ir = float(excess.mean() * 4.0 / expected_tracking_error)
    assert np.isclose(metrics["tracking_error_annualized"], expected_tracking_error)
    assert np.isclose(metrics["information_ratio"], expected_ir)


def test_compute_performance_metrics_total_return_is_interval_consistent() -> None:
    idx = pd.to_datetime(["2021-03-31", "2021-06-30", "2021-09-30"])
    strategy_nav = pd.Series([1.10, 1.21, 1.331], index=idx)
    benchmark_nav = pd.Series([1.00, 1.02, 1.03], index=idx)

    metrics = compute_performance_metrics(
        strategy_nav=strategy_nav,
        benchmark_nav=benchmark_nav,
        periods_per_year=4.0,
    )

    expected_total = float(strategy_nav.iloc[-1] / strategy_nav.iloc[0] - 1.0)
    expected_ann = float((1.0 + expected_total) ** (4.0 / (len(idx) - 1)) - 1.0)
    assert np.isclose(metrics["strategy_total_return"], expected_total)
    assert np.isclose(metrics["strategy_annualized_return"], expected_ann)


def test_compute_performance_metrics_total_return_prefers_period_returns() -> None:
    idx = pd.to_datetime(["2021-03-31", "2021-06-30", "2021-09-30"])
    strategy_returns = pd.Series([0.10, 0.10, 0.10], index=idx)
    benchmark_returns = pd.Series([0.02, 0.03, 0.04], index=idx)
    strategy_nav = pd.Series([1.10, 1.21, 1.331], index=idx)
    benchmark_nav = pd.Series([1.02, 1.0506, 1.092624], index=idx)

    metrics = compute_performance_metrics(
        strategy_nav=strategy_nav,
        benchmark_nav=benchmark_nav,
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        periods_per_year=4.0,
    )

    expected_strategy_total = float((1.0 + strategy_returns).prod() - 1.0)
    expected_benchmark_total = float((1.0 + benchmark_returns).prod() - 1.0)
    expected_strategy_ann = float((1.0 + expected_strategy_total) ** (4.0 / 3.0) - 1.0)
    assert np.isclose(metrics["strategy_total_return"], expected_strategy_total)
    assert np.isclose(metrics["benchmark_total_return"], expected_benchmark_total)
    assert np.isclose(metrics["strategy_annualized_return"], expected_strategy_ann)


def test_compute_performance_metrics_returns_empty_when_nav_has_no_overlap() -> None:
    strategy_nav = pd.Series(
        [1.0, 1.1],
        index=pd.to_datetime(["2021-03-31", "2021-06-30"]),
    )
    benchmark_nav = pd.Series(
        [1.0, 1.1],
        index=pd.to_datetime(["2022-03-31", "2022-06-30"]),
    )

    metrics = compute_performance_metrics(strategy_nav=strategy_nav, benchmark_nav=benchmark_nav)

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
                    "benchmark_next_period_return": 0.005,
                    "benchmark_cum_ret": 1.0 + 0.001 * len(rows),
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
    assert len(result.nav) == len(result.signal_nav)
    assert len(result.nav) == len(result.signal_period_profit)
    assert len(result.nav) == len(result.signal_turnover)
    assert len(result.nav) == len(result.signal_active_names)
    assert len(result.nav) > 0
    assert not result.nav.isna().any()
    assert not result.signal_nav.isna().any()
    assert not result.period_returns.isna().any()
    assert not result.signal_period_profit.isna().any()
    assert not result.period_turnover.isna().any()
    assert not result.signal_turnover.isna().any()
    assert {
        "target_gross",
        "realized_gross",
        "target_net",
        "realized_net",
        "unallocated_exposure",
        "qp_fallback",
    }.issubset(result.portfolio_diagnostics.columns)


def test_build_benchmark_nav_aligns_and_uses_canonical_name() -> None:
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-06-30"), "A"),
            (pd.Timestamp("2021-09-30"), "A"),
        ],
        names=["date", "ticker"],
    )
    frame = pd.DataFrame({"benchmark_cum_ret": [100.0, 110.0, 121.0]}, index=idx)
    target_index = pd.to_datetime(["2021-06-30", "2021-09-30"])

    benchmark_nav = build_benchmark_nav(frame=frame, target_index=target_index)

    assert benchmark_nav.name == "benchmark_nav"
    assert benchmark_nav.index.equals(target_index)
    assert np.isclose(float(benchmark_nav.iloc[0]), 1.0)
    assert np.isclose(float(benchmark_nav.iloc[1]), 1.1)


def test_build_benchmark_nav_supports_cumulative_return_mode() -> None:
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-06-30"), "A"),
            (pd.Timestamp("2021-09-30"), "A"),
        ],
        names=["date", "ticker"],
    )
    frame = pd.DataFrame({"benchmark_cum_ret": [0.0, 0.10, 0.21]}, index=idx)
    target_index = pd.to_datetime(["2021-03-31", "2021-06-30", "2021-09-30"])

    benchmark_nav = build_benchmark_nav(
        frame=frame,
        target_index=target_index,
        benchmark_cum_mode="cumulative_return",
    )

    assert np.allclose(benchmark_nav.to_numpy(), [1.0, 1.1, 1.21])


def test_run_rolling_backtest_missing_feature_policy_errors_by_default() -> None:
    raw = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-31", periods=8, freq="ME").repeat(2),
            "ticker": ["A", "B"] * 8,
            "f1": np.tile([1.0, -1.0], 8),
            "next_period_return": np.tile([0.02, -0.01], 8),
            "benchmark_next_period_return": 0.0,
            "benchmark_cum_ret": 1.0,
        }
    )
    frame = preprocess_data(raw, apply_global_fill=False)

    with pytest.raises(ValueError, match="missing_factor"):
        run_rolling_backtest(
            frame=frame,
            windows=[("2020-01-01", "2020-04-30", "2020-05-01", "2020-08-31")],
            feature_columns=["f1", "missing_factor"],
            model_params={"n_estimators": 5},
        )


def test_run_rolling_backtest_missing_feature_policy_can_fill_for_legacy() -> None:
    raw = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-31", periods=8, freq="ME").repeat(2),
            "ticker": ["A", "B"] * 8,
            "f1": np.tile([1.0, -1.0], 8),
            "next_period_return": np.tile([0.02, -0.01], 8),
            "benchmark_next_period_return": 0.0,
            "benchmark_cum_ret": 1.0,
        }
    )
    frame = preprocess_data(raw, apply_global_fill=False)

    with pytest.warns(RuntimeWarning, match="filling with 0.0"):
        result = run_rolling_backtest(
            frame=frame,
            windows=[("2020-01-01", "2020-04-30", "2020-05-01", "2020-08-31")],
            feature_columns=["f1", "missing_factor"],
            model_params={"n_estimators": 5},
            missing_feature_policy="warn_fill_zero",
        )

    assert len(result.nav) == 1


def test_holdout_missing_feature_policy_errors_by_default() -> None:
    dates = pd.date_range("2020-01-31", periods=8, freq="ME")
    raw = pd.DataFrame(
        {
            "date": dates.repeat(2),
            "ticker": ["A", "B"] * len(dates),
            "f1": np.tile([1.0, -1.0], len(dates)),
            "next_period_return": np.tile([0.02, -0.01], len(dates)),
            "benchmark_next_period_return": 0.0,
            "benchmark_cum_ret": 1.0,
        }
    )
    frame = preprocess_data(raw, apply_global_fill=False)
    settings = BacktestSettings(
        data="unused.parquet",
        holdout_start="2020-06-01",
        holdout_end="2020-08-31",
    )

    with pytest.raises(ValueError, match="missing_factor"):
        _build_holdout_result(
            frame=frame,
            holdout_start=settings.holdout_start,
            holdout_end=settings.holdout_end,
            model_segment="segment_b",
            segment_fit=SegmentFitResult(
                feature_columns=["f1", "missing_factor"],
                model_params={"n_estimators": 5},
                model_id="random_forest",
                train_start="2020-01-01",
                train_end="2020-05-31",
                valid_start="2020-06-01",
                valid_end="2020-08-31",
                validation_profit=0.0,
                validation_turnover=0.0,
                validation_active_names=0,
                tuning_best_value=float("nan"),
                tuning_enabled=False,
                selection_history=None,
            ),
            settings=settings,
            portfolio_cfg=build_portfolio_config(settings),
            model_adapter=type(
                "Adapter",
                (),
                {"training_target_column": "rel_performance"},
            )(),
            market_profile=get_market_profile("cn"),
        )


def test_build_notebook_report_artifacts_exports_nav_beta_and_residuals() -> None:
    idx = pd.to_datetime(["2021-03-31", "2021-06-30", "2021-09-30", "2021-12-31"])
    strategy_ret = pd.Series([0.05, 0.02, -0.01, 0.03], index=idx, name="strategy_ret")
    benchmark_ret = pd.Series([0.02, 0.01, -0.005, 0.01], index=idx, name="benchmark_ret")
    strategy_nav = (1.0 + strategy_ret).cumprod().rename("strategy_nav")
    benchmark_nav = (1.0 + benchmark_ret).cumprod().rename("benchmark_nav")
    signal_nav = pd.Series([1.0, 1.03, 1.02, 1.05], index=idx, name="signal_nav")

    report = build_notebook_report_artifacts(
        strategy_nav=strategy_nav,
        benchmark_nav=benchmark_nav,
        signal_nav=signal_nav,
        strategy_returns=strategy_ret,
        benchmark_returns=benchmark_ret,
        rolling_beta_window=3,
        residual_bins=4,
    )

    assert {"strategy_nav", "benchmark_nav", "signal_nav", "hedged_nav"}.issubset(report.navs.columns)
    assert report.rolling_beta.name == "rolling_beta"
    assert report.residual_returns.name == "residual_return"
    assert list(report.residual_distribution.columns) == ["bin_left", "bin_right", "count", "density"]
