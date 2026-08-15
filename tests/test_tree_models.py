from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from moneytree.models import get_model_adapter


def _panel(days: int = 12, tickers: list[str] | None = None) -> pd.DataFrame:
    tickers = tickers or ["A", "B", "C"]
    dates = pd.date_range("2021-01-04", periods=days, freq="B")
    rows: list[dict[str, object]] = []
    for date in dates:
        for idx, ticker in enumerate(tickers):
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "f1": idx + dates.get_loc(date) * 0.1,
                    "f2": (3 - idx) + dates.get_loc(date) * 0.01,
                }
            )
    frame = pd.DataFrame(rows).set_index(["date", "ticker"]).sort_index()
    return frame


def _train_y(frame: pd.DataFrame) -> np.ndarray:
    return ((frame["f1"] - frame["f2"]) > 0).astype(int) * 2 - 1


SKLEARN_TREE_IDS = ("extra_trees", "gradient_boosting", "hist_gradient_boosting")


@pytest.mark.parametrize("model_id", SKLEARN_TREE_IDS)
def test_sklearn_tree_adapter_fits_and_predicts(model_id: str) -> None:
    adapter = get_model_adapter(model_id)
    frame = _panel()
    train_x = frame.drop(columns=["f2"])
    train_y = _train_y(frame)

    model = adapter.fit(train_x=train_x, train_y=train_y, random_state=7)
    outputs = adapter.predict_outputs(model=model, features=train_x)

    assert outputs.scores.shape == (len(train_x),)
    assert np.isfinite(outputs.scores).all()
    assert outputs.probabilities is not None
    assert adapter.capabilities.supports_probability_scores


@pytest.mark.parametrize("model_id", ("extra_trees", "gradient_boosting"))
def test_sklearn_tree_adapter_importance_selection(model_id: str) -> None:
    adapter = get_model_adapter(model_id)
    frame = _panel()
    train_x = frame.drop(columns=["f2"])
    train_y = _train_y(frame)

    importance = adapter.select_features(
        method="importance",
        train_x=train_x,
        train_y=train_y,
        valid_x=train_x,
        valid_returns=np.zeros(len(train_x)),
        params=adapter.default_params(),
        random_state=7,
        min_features=1,
        max_steps=1,
        cost_bps=0.0,
    )
    assert importance.selected_features == ["f1"]


@pytest.mark.parametrize("model_id", SKLEARN_TREE_IDS)
def test_sklearn_tree_adapter_rejects_unsupported_tuning(model_id: str) -> None:
    adapter = get_model_adapter(model_id)
    with pytest.raises(ValueError, match="does not support hyperparameter tuning"):
        adapter.validate_configuration(feature_selection="none", n_trials=1)


def test_xgb_ranker_reports_missing_optional_dependency() -> None:
    if importlib.util.find_spec("xgboost") is not None:
        pytest.skip("xgboost is installed in this environment")
    adapter = get_model_adapter("xgb_ranker")
    with pytest.raises(RuntimeError, match="optional xgboost dependency"):
        adapter.fit(
            train_x=pd.DataFrame({"f1": [1.0, 2.0, 3.0]}),
            train_y=np.array([-1, 0, 1]),
            random_state=7,
        )


def test_xgb_ranker_derives_group_sizes_from_date_level() -> None:
    if importlib.util.find_spec("xgboost") is None:
        pytest.skip("xgboost is not installed in this environment")
    frame = _panel()
    train_x = frame.drop(columns=["f2"])

    adapter = get_model_adapter("xgb_ranker")
    groups = adapter._derive_group_sizes(train_x)

    assert groups == [3] * 12


def test_xgb_ranker_fits_and_predicts_with_groups() -> None:
    if importlib.util.find_spec("xgboost") is None:
        pytest.skip("xgboost is not installed in this environment")
    frame = _panel()
    train_x = frame.drop(columns=["f2"])
    train_y = _train_y(frame)

    adapter = get_model_adapter("xgb_ranker")
    model = adapter.fit(
        train_x=train_x,
        train_y=train_y,
        params={"n_estimators": 10, "max_depth": 2},
        random_state=7,
    )
    outputs = adapter.predict_outputs(model=model, features=train_x)

    assert outputs.scores.shape == (len(train_x),)
    assert np.isfinite(outputs.scores).all()
    assert not adapter.capabilities.supports_probability_scores
