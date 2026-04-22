from __future__ import annotations

import pandas as pd
import pytest

from treealpha.config import BacktestSettings
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


def test_cn_market_profile_normalizes_configured_benchmark_aliases() -> None:
    profile = get_market_profile("cn")
    frame = pd.DataFrame(
        {
            "date": ["2021-01-31"],
            "ticker": ["000001.SZ"],
            "next_period_return": [0.01],
            "index_next": [0.002],
            "index_cum": [100.0],
            "is_suspended": [False],
            "is_st": [False],
            "hit_up_limit": [False],
            "hit_down_limit": [False],
        }
    )
    settings = BacktestSettings(
        data="dummy.parquet",
        market_profile="cn",
        benchmark_name="000300.SH",
        benchmark_return_column="index_next",
        benchmark_cum_column="index_cum",
        market_tradability_columns={
            "suspend": "is_suspended",
            "st": "is_st",
            "up_limit": "hit_up_limit",
            "down_limit": "hit_down_limit",
        },
        market_tradability_filters={
            "suspend": True,
            "st": True,
            "up_limit": True,
            "down_limit": True,
        },
    )

    prepared = profile.prepare_frame(frame=frame, label_source="actual", settings=settings)

    assert "benchmark_next_period_return" in prepared.columns
    assert "benchmark_cum_ret" in prepared.columns
    assert float(prepared.loc[0, "benchmark_next_period_return"]) == 0.002
    assert float(prepared.loc[0, "benchmark_cum_ret"]) == 100.0


def test_cn_market_profile_requires_configured_tradability_columns_when_enabled() -> None:
    profile = get_market_profile("cn")
    frame = pd.DataFrame(
        {
            "date": ["2021-01-31"],
            "ticker": ["000001.SZ"],
            "next_period_return": [0.01],
            "benchmark_next_period_return": [0.002],
            "benchmark_cum_ret": [100.0],
            "is_suspended": [False],
        }
    )
    settings = BacktestSettings(
        data="dummy.parquet",
        market_profile="cn",
        market_tradability_columns={"suspend": "is_suspended"},
        market_tradability_filters={"suspend": True, "st": True},
    )

    with pytest.raises(ValueError, match="tradability column mapping for 'st'"):
        profile.prepare_frame(frame=frame, label_source="actual", settings=settings)


def test_cn_market_profile_filters_suspended_st_and_limit_hit_rows() -> None:
    profile = get_market_profile("cn")
    frame = pd.DataFrame(
        {
            "next_period_return": [0.01, 0.02, 0.03, 0.04, 0.05],
            "benchmark_next_period_return": [0.0] * 5,
            "benchmark_cum_ret": [100.0] * 5,
            "is_suspended": [False, True, False, False, False],
            "is_st": [False, False, True, False, False],
            "hit_up_limit": [False, False, False, True, False],
            "hit_down_limit": [False, False, False, False, True],
        },
        index=pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2021-01-31"), "000001.SZ"),
                (pd.Timestamp("2021-01-31"), "000002.SZ"),
                (pd.Timestamp("2021-01-31"), "000003.SZ"),
                (pd.Timestamp("2021-01-31"), "000004.SZ"),
                (pd.Timestamp("2021-01-31"), "000005.SZ"),
            ],
            names=["date", "ticker"],
        ),
    )
    settings = BacktestSettings(
        data="dummy.parquet",
        market_profile="cn",
        market_tradability_columns={
            "suspend": "is_suspended",
            "st": "is_st",
            "up_limit": "hit_up_limit",
            "down_limit": "hit_down_limit",
        },
        market_tradability_filters={
            "suspend": True,
            "st": True,
            "up_limit": True,
            "down_limit": True,
        },
    )

    filtered = profile.filter_tradable_frame(frame, settings=settings)

    assert list(filtered.index.get_level_values("ticker")) == ["000001.SZ"]
