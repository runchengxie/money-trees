from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _inference_module():
    module_path = Path(__file__).parents[1] / "src/moneytree/factors/inference.py"
    assert module_path.is_file(), "factor inference module has not been added"
    return importlib.import_module("moneytree.factors.inference")


def test_hac_mean_uses_requested_dependence_lag() -> None:
    inference = _inference_module()
    assert hasattr(inference, "estimate_mean_hac")

    result = inference.estimate_mean_hac(
        [-1.0, 1.0, -1.0, 1.0], holding_period_days=2
    )

    assert result["status"] == "complete"
    assert result["method"] == "newey_west_hac"
    assert result["estimate"] == pytest.approx(0.0)
    assert result["standard_error"] == pytest.approx(0.25)
    assert result["lags"] == 1
    assert result["p_value"] == pytest.approx(1.0)


def test_hac_mean_reports_insufficient_sample_and_rejects_invalid_horizon() -> None:
    inference = _inference_module()
    assert hasattr(inference, "estimate_mean_hac")

    result = inference.estimate_mean_hac([0.1], holding_period_days=1)

    assert result["status"] == "not_provided"
    assert result["reason"] == "insufficient_valid_observations"
    with pytest.raises(ValueError, match="holding_period_days must be at least 1"):
        inference.estimate_mean_hac([0.1, 0.2], holding_period_days=0)


def test_hac_mean_preserves_missing_date_gaps_in_lag_calculation() -> None:
    inference = _inference_module()

    result = inference.estimate_mean_hac(
        [1.0, float("nan"), -1.0], holding_period_days=2
    )

    assert result["standard_error"] == pytest.approx(2**-0.5)


def test_adjust_pvalues_reports_by_and_bh_over_full_factor_family() -> None:
    inference = _inference_module()
    assert hasattr(inference, "adjust_pvalues")

    adjusted = inference.adjust_pvalues(
        {"alpha_a": 0.01, "alpha_b": 0.04, "alpha_c": 0.03, "alpha_missing": None}
    )

    assert adjusted["alpha_a"]["q_value_bh"] == pytest.approx(0.04)
    assert adjusted["alpha_b"]["q_value_bh"] == pytest.approx(0.0533333333)
    assert adjusted["alpha_a"]["q_value_by"] == pytest.approx(0.0833333333)
    assert adjusted["alpha_b"]["q_value_by"] == pytest.approx(0.1111111111)
    assert adjusted["alpha_missing"]["raw_p_value"] is None
    assert adjusted["alpha_missing"]["q_value_by"] is None


def test_adjust_pvalues_rejects_values_outside_probability_range() -> None:
    inference = _inference_module()
    assert hasattr(inference, "adjust_pvalues")

    with pytest.raises(ValueError, match="p-values must be between 0 and 1"):
        inference.adjust_pvalues({"alpha_a": 1.1})
