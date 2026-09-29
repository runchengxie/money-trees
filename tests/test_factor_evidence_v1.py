from __future__ import annotations

import pytest

from moneytree.factors.evidence_v1 import build_factor_evidence_v1


def _snapshot() -> dict:
    return {
        "kind": "moneytree_factor_evidence_snapshot",
        "schema_version": "1.0",
        "data_version": "cn-test",
        "dataset": {"observation_count": 10},
        "factors": [
            {
                "name": "alpha158_001",
                "family": "alpha158",
                "ic": {"mean": 0.03, "ir": 0.4},
                "rank_ic": {"mean": 0.04, "ir": 0.5},
                "coverage": {"ratio": 0.9},
            }
        ],
    }


def test_build_factor_evidence_v1_groups_research_evidence() -> None:
    result = build_factor_evidence_v1(
        _snapshot(),
        uncertainty={"method": "block_bootstrap", "status": "complete"},
        risk={"status": "complete", "cvar_95": -0.12},
        residual={"status": "complete", "max_abs_ic": 0.01},
        temporal_validation={"status": "complete", "purged_folds": 5},
    )

    assert result["schema_version"] == "factor_evidence.v1"
    assert result["artifact_type"] == "factor_evidence"
    assert result["predictive"]["factors"][0]["name"] == "alpha158_001"
    assert result["uncertainty"]["method"] == "block_bootstrap"
    assert result["risk"]["cvar_95"] == -0.12


def test_build_factor_evidence_v1_rejects_private_fields() -> None:
    snapshot = _snapshot()
    snapshot["factors"][0]["ticker"] = "000001.SZ"

    with pytest.raises(ValueError, match="Forbidden public field"):
        build_factor_evidence_v1(snapshot)
