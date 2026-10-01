from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import sqrt
from typing import Any

import numpy as np
from scipy.stats import norm


def estimate_mean_hac(
    values: Sequence[float],
    *,
    holding_period_days: int,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """Estimate mean uncertainty with Newey-West Bartlett HAC covariance."""
    if holding_period_days < 1:
        raise ValueError("holding_period_days must be at least 1")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between 0 and 1")

    sample = np.asarray(values, dtype=float)
    valid = np.isfinite(sample)
    count = int(valid.sum())
    if count < 2:
        return {
            "status": "not_provided",
            "reason": "insufficient_valid_observations",
            "observations": count,
            "holding_period_days": holding_period_days,
        }

    estimate = float(sample[valid].mean())
    centered = np.zeros_like(sample)
    centered[valid] = sample[valid] - estimate
    lags = min(holding_period_days - 1, len(sample) - 1)
    long_run_variance = float(np.dot(centered, centered) / count)
    for lag in range(1, lags + 1):
        valid_pairs = valid[lag:] & valid[:-lag]
        autocovariance = float(
            np.dot(centered[lag:][valid_pairs], centered[:-lag][valid_pairs]) / count
        )
        weight = 1.0 - lag / (lags + 1.0)
        long_run_variance += 2.0 * weight * autocovariance
    standard_error = sqrt(max(long_run_variance, 0.0) / count)
    if standard_error == 0:
        return {
            "status": "not_provided",
            "reason": "zero_hac_variance",
            "estimate": estimate,
            "observations": count,
            "holding_period_days": holding_period_days,
            "lags": lags,
        }

    critical_value = float(norm.ppf((1.0 + confidence_level) / 2.0))
    z_score = estimate / standard_error
    return {
        "status": "complete",
        "method": "newey_west_hac",
        "reference_distribution": "standard_normal",
        "estimate": estimate,
        "standard_error": standard_error,
        "confidence_level": confidence_level,
        "confidence_interval": [
            estimate - critical_value * standard_error,
            estimate + critical_value * standard_error,
        ],
        "p_value": float(2.0 * norm.sf(abs(z_score))),
        "observations": count,
        "holding_period_days": holding_period_days,
        "lags": lags,
        "kernel": "bartlett",
    }


def adjust_pvalues(
    p_values: Mapping[str, float | None],
) -> dict[str, dict[str, float | None]]:
    """Return BY and BH q-values over the complete declared factor family."""
    family_size = len(p_values)
    valid: list[tuple[str, float]] = []
    for factor, value in p_values.items():
        if value is None:
            continue
        probability = float(value)
        if not np.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError("p-values must be between 0 and 1")
        valid.append((str(factor), probability))

    ordered = sorted(valid, key=lambda item: (item[1], item[0]))
    harmonic_factor = sum(1.0 / index for index in range(1, family_size + 1))

    def step_up(multiplier: float) -> dict[str, float]:
        adjusted: dict[str, float] = {}
        running_minimum = 1.0
        for index in range(len(ordered), 0, -1):
            factor, probability = ordered[index - 1]
            candidate = probability * family_size * multiplier / index
            running_minimum = min(running_minimum, candidate)
            adjusted[factor] = min(1.0, running_minimum)
        return adjusted

    bh = step_up(1.0)
    by = step_up(harmonic_factor)
    return {
        factor: {
            "raw_p_value": float(value) if value is not None else None,
            "q_value_bh": bh.get(factor),
            "q_value_by": by.get(factor),
        }
        for factor, value in p_values.items()
    }
