from __future__ import annotations

import numpy as np
import pandas as pd

from moneytree.model import (
    estimate_turnover,
    profit_with_estimated_turnover,
    score_predictions_over_time,
    sequential_feature_selection,
    signal_profit,
    tune_random_forest,
)


def test_signal_profit_all_zero_predictions_returns_zero() -> None:
    preds = np.array([0, 0, 0])
    realized = np.array([0.02, -0.01, 0.03])
    assert signal_profit(preds, realized, cost_bps=20.0) == 0.0


def test_signal_profit_cost_penalty_increases_with_cost_bps() -> None:
    preds = np.array([1, -1, 0, 1])
    realized = np.array([0.03, -0.01, 0.02, 0.01])
    low_cost = signal_profit(preds, realized, cost_bps=5.0, turnover=0.8)
    high_cost = signal_profit(preds, realized, cost_bps=25.0, turnover=0.8)
    assert high_cost < low_cost


def test_signal_profit_default_turnover_matches_flat_open_assumption() -> None:
    preds = np.array([1, -1, 1, -1])
    realized = np.array([0.02, -0.01, 0.03, -0.02])
    implied = signal_profit(preds, realized, cost_bps=20.0)
    explicit = signal_profit(preds, realized, cost_bps=20.0, turnover=0.5)
    assert np.isclose(implied, explicit)


def test_estimate_turnover_open_switch_and_close_positions() -> None:
    open_book = pd.Series({"A": 0.5, "B": -0.5}, dtype=float)
    switched_book = pd.Series({"A": 0.5, "C": -0.5}, dtype=float)
    flat_book = pd.Series(dtype=float)

    open_turnover = estimate_turnover(open_book, previous_weights=None)
    switch_turnover = estimate_turnover(switched_book, previous_weights=open_book)
    close_turnover = estimate_turnover(flat_book, previous_weights=switched_book)

    assert np.isclose(open_turnover, 0.5)
    assert np.isclose(switch_turnover, 0.5)
    assert np.isclose(close_turnover, 0.5)


def test_profit_with_estimated_turnover_uses_sample_index() -> None:
    preds = np.array([1, -1, -1], dtype=int)
    realized = np.array([0.01, -0.02, 0.03], dtype=float)
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2020-03-31"), "A"),
            (pd.Timestamp("2020-03-31"), "A"),
            (pd.Timestamp("2020-03-31"), "B"),
        ],
        names=["date", "ticker"],
    )

    profit, current_weights, turnover = profit_with_estimated_turnover(
        predictions=preds,
        realized_returns=realized,
        cost_bps=10.0,
        sample_index=idx,
        previous_weights=None,
    )

    assert set(current_weights.index.tolist()) == {"A", "B"}
    assert np.isclose(turnover, 0.5)
    explicit = signal_profit(preds, realized, cost_bps=10.0, turnover=turnover)
    assert np.isclose(profit, explicit)


def test_sequential_feature_selection_respects_min_features() -> None:
    rng = np.random.default_rng(7)
    cols = ["f1", "f2", "f3", "f4"]
    train_x = pd.DataFrame(rng.normal(size=(200, len(cols))), columns=cols)
    train_y = rng.choice([-1, 0, 1], size=200)
    valid_x = pd.DataFrame(rng.normal(size=(120, len(cols))), columns=cols)
    valid_returns = rng.normal(loc=0.001, scale=0.02, size=120)

    result = sequential_feature_selection(
        train_x=train_x,
        train_y=train_y,
        valid_x=valid_x,
        valid_returns=valid_returns,
        params={
            "n_estimators": 20,
            "max_depth": 6,
            "min_samples_leaf": 2,
            "max_features": "sqrt",
        },
        random_state=11,
        min_features=2,
        max_steps=10,
    )

    assert len(result.selected_features) >= 2
    assert set(result.selected_features).issubset(set(cols))


def test_score_predictions_over_time_uses_date_groups_with_turnover() -> None:
    preds = np.array([1, -1, 1, -1], dtype=int)
    realized = np.array([0.02, -0.01, 0.01, -0.02], dtype=float)
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2020-03-31"), "A"),
            (pd.Timestamp("2020-03-31"), "B"),
            (pd.Timestamp("2020-06-30"), "A"),
            (pd.Timestamp("2020-06-30"), "B"),
        ],
        names=["date", "ticker"],
    )
    score = score_predictions_over_time(
        predictions=preds,
        realized_returns=realized,
        sample_index=idx,
        cost_bps=10.0,
    )
    assert np.isfinite(score)


def test_tune_random_forest_supports_time_series_cv() -> None:
    rng = np.random.default_rng(13)
    dates = pd.date_range("2018-03-31", periods=12, freq="QE")
    tickers = ["A", "B", "C"]
    index = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    train_x = pd.DataFrame(
        {
            "f1": rng.normal(size=len(index)),
            "f2": rng.normal(size=len(index)),
        },
        index=index,
    )
    train_y = rng.choice([-1, 0, 1], size=len(index))
    train_returns = rng.normal(loc=0.001, scale=0.02, size=len(index))
    valid_x = train_x.iloc[:6]
    valid_returns = train_returns[:6]

    best_params, best_value = tune_random_forest(
        train_x=train_x,
        train_y=train_y,
        train_returns=train_returns,
        valid_x=valid_x,
        valid_returns=valid_returns,
        n_trials=1,
        random_state=5,
        tuning_cv_folds=3,
    )

    assert {"min_samples_leaf", "max_depth", "n_estimators", "max_features"} == set(
        best_params.keys()
    )
    assert np.isfinite(best_value)
