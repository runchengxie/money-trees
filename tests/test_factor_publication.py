from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from moneytree.factors.publication import build_factor_evidence_snapshot


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
    assert payload["schema_version"] == "1.0"
    assert payload["data_version"] == "fixture-v1"
    assert payload["code_revision"] == "abc123"
    assert payload["dataset"]["date_start"] == "2024-01-02"
    assert payload["dataset"]["date_end"] == "2024-01-03"
    assert payload["factors"][0]["name"] == "alpha001"
    assert "group_returns" in payload["factors"][0]
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
