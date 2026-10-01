from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from moneytree.factors import publication
from moneytree.factors.publication import audit_public_snapshot, build_factor_evidence_snapshot


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"]
            ),
            "ticker": ["A", "B", "A", "B"],
            "alpha001": [1.0, 2.0, 2.0, 1.0],
            "alpha_empty": [np.nan, np.nan, np.nan, np.nan],
            "next_period_return": [0.01, -0.01, 0.02, -0.02],
            "private_weight": [0.5, 0.5, 0.4, 0.6],
        }
    )


def test_public_snapshot_contains_aggregate_factor_evidence_only() -> None:
    payload = build_factor_evidence_snapshot(
        _panel(),
        ["alpha001"],
        data_version="fixture-v1",
        config={"group_count": 2},
        git_metadata={"revision": "abc123", "dirty": False},
    )

    assert payload["kind"] == "moneytree_factor_evidence_snapshot"
    assert payload["schema_version"] == "1.1"
    assert payload["data_version"] == "fixture-v1"
    assert payload["code_revision"] == "abc123"
    assert payload["dataset"]["date_start"] == "2024-01-02"
    assert payload["dataset"]["date_end"] == "2024-01-03"
    assert payload["factors"][0]["name"] == "alpha001"
    assert "group_returns" in payload["factors"][0]
    assert payload["factors"][0]["annual_slices"][0]["label"] == "2024"
    assert payload["factors"][0]["annual_slices"][0]["valid_dates"] == 2
    assert payload["factors"][0]["annual_slices"][0]["rank_ic_mean"] == pytest.approx(0.0)
    assert payload["factors"][0]["regime_slices"] == []
    assert payload["temporal_validation"]["market_regime"]["reason"] == "benchmark_returns_not_supplied"
    assert payload["factors"][0]["uncertainty"]["status"] == "not_provided"
    assert payload["multiple_testing"]["status"] == "not_provided"
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    assert "private_weight" not in encoded
    assert '"ticker"' not in encoded


def test_public_snapshot_keeps_factor_with_no_valid_observations() -> None:
    payload = build_factor_evidence_snapshot(_panel(), ["alpha_empty"])

    factor = payload["factors"][0]
    assert factor["name"] == "alpha_empty"
    assert factor["coverage"]["valid_observations"] == 0
    assert factor["ic"]["mean"] is None
    assert factor["rank_ic"]["mean"] is None
    assert factor["uncertainty"]["status"] == "not_provided"


def test_public_snapshot_rejects_missing_panel_contract() -> None:
    with pytest.raises(KeyError, match="Missing required panel columns"):
        build_factor_evidence_snapshot(
            _panel().drop(columns=["next_period_return"]), ["alpha001"]
        )


def test_public_snapshot_normalizes_non_finite_values_to_json_null() -> None:
    panel = _panel()
    panel["next_period_return"] = np.inf
    payload = build_factor_evidence_snapshot(panel, ["alpha001"])

    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    assert payload["factors"][0]["ic"]["mean"] is None


def test_annual_temporal_slices_group_daily_rank_ic_and_group_returns() -> None:
    assert hasattr(publication, "build_temporal_slices")
    daily_metrics = {
        "alpha001": [
            {"date": "2023-12-29", "rank_ic": 0.1},
            {"date": "2024-01-02", "rank_ic": -0.1},
            {"date": "2024-01-03", "rank_ic": 0.3},
        ]
    }
    daily_group_returns = {
        "alpha001": [
            {"date": "2024-01-02", "group": 1, "mean_return": -0.02},
            {"date": "2024-01-02", "group": 2, "mean_return": 0.02},
            {"date": "2024-01-03", "group": 1, "mean_return": -0.01},
            {"date": "2024-01-03", "group": 2, "mean_return": 0.01},
        ]
    }

    result = publication.build_temporal_slices(daily_metrics, daily_group_returns)

    annual = result["annual"]["alpha001"]
    assert [item["label"] for item in annual] == ["2023", "2024"]
    assert [item["valid_dates"] for item in annual] == [1, 2]
    assert [item["rank_ic_mean"] for item in annual] == pytest.approx([0.1, 0.1])
    assert [item["rank_ic_positive_rate"] for item in annual] == [1.0, 0.5]
    assert annual[0]["group_returns"] == []
    assert annual[1]["group_returns"] == [
        {"group": 1, "mean_return": pytest.approx(-0.015), "periods": 2},
        {"group": 2, "mean_return": pytest.approx(0.015), "periods": 2},
    ]


def test_market_regime_uses_only_complete_prior_benchmark_window() -> None:
    assert hasattr(publication, "build_temporal_slices")
    dates = pd.bdate_range("2023-01-02", periods=255)
    benchmark = pd.Series(0.001, index=dates)
    benchmark.iloc[252:] = -0.5
    metrics = {
        "alpha001": [
            {"date": date, "rank_ic": 0.2 if index < 254 else -0.2}
            for index, date in enumerate(dates)
        ]
    }

    result = publication.build_temporal_slices(
        metrics,
        {"alpha001": []},
        benchmark_returns=benchmark,
        regime_window=252,
        benchmark_name="fixture_index",
    )

    factor_regimes = result["regime"]["alpha001"]
    assert [item["label"] for item in factor_regimes] == ["bull", "bear"]
    assert [item["valid_dates"] for item in factor_regimes] == [1, 2]
    assert factor_regimes[0]["rank_ic_mean"] == pytest.approx(0.2)
    assert factor_regimes[1]["rank_ic_mean"] == pytest.approx(0.0)
    assert result["regime_metadata"]["benchmark_name"] == "fixture_index"


def test_market_regime_is_unavailable_without_benchmark() -> None:
    assert hasattr(publication, "build_temporal_slices")
    result = publication.build_temporal_slices({"alpha001": []}, {"alpha001": []})

    assert result["regime_status"]["status"] == "not_provided"
    assert result["regime_status"]["reason"] == "benchmark_returns_not_supplied"


def test_market_regime_is_unavailable_when_window_misses_factor_dates() -> None:
    benchmark = pd.Series(
        [0.01, 0.01, 0.01],
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )
    result = publication.TemporalSliceAccumulator(
        ["alpha001"],
        benchmark_returns=benchmark,
        regime_window=2,
        benchmark_name="fixture_index",
    )
    result.update(pd.Timestamp("2020-01-02"), {"alpha001": 0.1}, {})

    assert result.result()["regime_status"]["status"] == "not_provided"
    assert result.result()["regime_status"]["reason"] == (
        "benchmark_window_does_not_overlap_factor_dates"
    )


def test_market_regime_rejects_conflicting_benchmark_values_on_same_date() -> None:
    benchmark = pd.Series(
        [0.01, 0.02],
        index=pd.to_datetime(["2024-01-02", "2024-01-02"]),
    )

    with pytest.raises(ValueError, match="agree within each date"):
        publication.build_temporal_slices(
            {"alpha001": []},
            {"alpha001": []},
            benchmark_returns=benchmark,
            regime_window=1,
            benchmark_name="fixture_index",
        )


def test_public_snapshot_rejects_forward_return_as_benchmark() -> None:
    with pytest.raises(ValueError, match="must not match forward return column"):
        build_factor_evidence_snapshot(
            _panel(),
            ["alpha001"],
            benchmark_return_column="next_period_return",
            benchmark_name="invalid_forward_target",
        )


def test_public_snapshot_adds_hac_and_multiple_testing_when_horizon_is_known() -> None:
    payload = build_factor_evidence_snapshot(
        _panel(),
        ["alpha001", "alpha_empty"],
        holding_period_days=1,
        config={"group_count": 2},
    )

    assert payload["uncertainty"]["status"] == "partial"
    assert payload["uncertainty"]["method"] == "newey_west_hac"
    assert payload["multiple_testing"]["method"] == "benjamini_yekutieli"
    assert payload["multiple_testing"]["family_size"] == 2
    assert payload["multiple_testing"]["tested_count"] == 1
    assert payload["factors"][0]["uncertainty"]["multiple_testing"]["q_value_by"] == pytest.approx(1.0)
    assert payload["factors"][1]["uncertainty"]["reason"] == "insufficient_valid_observations"


def test_810_factor_snapshot_keeps_corrected_evidence_aggregate_only() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"]
            ),
            "ticker": ["A", "B", "A", "B"],
            "next_period_return": [0.01, -0.01, 0.01, -0.01],
            **{
                f"alpha{index:03d}": [1.0, 2.0, 2.0, 1.0]
                for index in range(810)
            },
        }
    )
    factors = [f"alpha{index:03d}" for index in range(810)]

    payload = build_factor_evidence_snapshot(
        frame,
        factors,
        holding_period_days=1,
        config={"group_count": 2},
    )
    audit_public_snapshot(payload)
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)

    assert payload["multiple_testing"]["family_size"] == 810
    assert payload["multiple_testing"]["tested_count"] == 810
    assert all(
        factor["uncertainty"]["multiple_testing"]["q_value_by"] == pytest.approx(1.0)
        for factor in payload["factors"]
    )
    assert '"ticker"' not in encoded
