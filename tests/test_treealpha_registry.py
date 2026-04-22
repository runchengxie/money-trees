from __future__ import annotations

import pandas as pd
import pytest

from treealpha.markets import get_market_profile
from treealpha.models import get_model_adapter


def test_model_registry_resolves_expected_builtin_ids() -> None:
    assert get_model_adapter("random_forest").model_id == "random_forest"
    assert get_model_adapter("ridge").model_id == "ridge"
    assert get_model_adapter("lasso").model_id == "lasso"
    assert get_model_adapter("elasticnet").model_id == "elasticnet"
    assert get_model_adapter("xgboost").model_id == "xgboost"


def test_linear_model_rejects_unsupported_feature_selection_and_tuning() -> None:
    adapter = get_model_adapter("ridge")

    with pytest.raises(ValueError, match="does not support feature_selection"):
        adapter.validate_configuration(feature_selection="importance", n_trials=0)

    with pytest.raises(ValueError, match="does not support hyperparameter tuning"):
        adapter.validate_configuration(feature_selection="none", n_trials=1)


def test_xgboost_adapter_reports_missing_optional_dependency() -> None:
    adapter = get_model_adapter("xgboost")
    with pytest.raises(RuntimeError, match="optional xgboost dependency"):
        adapter.fit(
            train_x=pd.DataFrame({"f1": [1.0, 2.0, 3.0]}),
            train_y=pd.Series([-1, 0, 1]).to_numpy(),
            params=None,
            random_state=7,
        )


def test_us_market_profile_validates_required_columns() -> None:
    profile = get_market_profile("us")
    frame = pd.DataFrame(
        {
            "date": ["2021-01-31"],
            "ticker": ["A"],
            "next_period_return": [0.01],
            "spy_cum_ret": [100.0],
        }
    )
    with pytest.raises(ValueError, match="missing required columns"):
        profile.validate_frame(frame=frame, label_source="actual")


def test_us_market_profile_adds_generic_benchmark_aliases() -> None:
    profile = get_market_profile("us")
    frame = pd.DataFrame(
        {
            "date": ["2021-01-31"],
            "ticker": ["A"],
            "next_period_return": [0.01],
            "spy_next_period_return": [0.002],
            "spy_cum_ret": [100.0],
        }
    )
    prepared = profile.prepare_frame(frame=frame, label_source="actual")
    assert "benchmark_next_period_return" in prepared.columns
    assert "benchmark_cum_ret" in prepared.columns
