from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.model import sequential_feature_selection, signal_profit


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
