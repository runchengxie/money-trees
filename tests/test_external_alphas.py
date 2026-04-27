from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from moneytree.factors.external import (
    ExternalAlphaInputError,
    ExternalAlphaValidationError,
    UnsupportedExternalAlphaFamilyError,
    build_dolphindb_input,
    build_external_alpha_manifest,
    external_alpha_columns,
    manifest_contains_secret_text,
    merge_external_alpha_columns,
    normalize_external_family,
    validate_date_ticker_keys,
    validate_external_alpha_columns,
)


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-04", "2021-01-05"]),
            "ticker": ["000001.SZ", "000001.SZ"],
            "open": [10.0, 10.5],
            "high": [10.2, 10.8],
            "low": [9.8, 10.2],
            "close": [10.1, 10.6],
            "vwap": [10.05, 10.55],
            "open_adj": [20.0, 20.5],
            "high_adj": [20.2, 20.8],
            "low_adj": [19.8, 20.2],
            "close_adj": [20.1, 20.6],
            "vwap_adj": [20.05, 20.55],
            "volume": [1000.0, 1100.0],
            "circ_mv": [10000.0, 10100.0],
            "industry": ["bank", "bank"],
            "benchmark_open": [4000.0, 4010.0],
            "benchmark_close": [4005.0, 4015.0],
        }
    )


def _alpha_output(family: str, panel: pd.DataFrame | None = None, value: float = 1.0) -> pd.DataFrame:
    source = _panel() if panel is None else panel
    values = {
        "tradetime": pd.to_datetime(source["date"]),
        "securityid": source["ticker"].astype(str),
    }
    values.update({column: value for column in external_alpha_columns(family)})
    return pd.DataFrame(values)


def test_external_alpha_columns_and_family_validation() -> None:
    assert normalize_external_family(" Alpha101 ") == "alpha101"
    assert external_alpha_columns("alpha101")[0] == "alpha101_001"
    assert external_alpha_columns("alpha101")[-1] == "alpha101_101"
    assert len(external_alpha_columns("alpha191")) == 191

    with pytest.raises(UnsupportedExternalAlphaFamilyError, match="alpha101, alpha191"):
        external_alpha_columns("alpha158")


def test_build_dolphindb_input_prefers_adjusted_fields() -> None:
    ddb_input, summary = build_dolphindb_input(_panel(), ["alpha101"])

    assert list(ddb_input.columns) == [
        "tradetime",
        "securityid",
        "open",
        "high",
        "low",
        "close",
        "vwap",
        "vol",
        "cap",
        "indclass",
        "index_open",
        "index_close",
    ]
    assert float(ddb_input.iloc[0]["open"]) == 20.0
    assert float(ddb_input.iloc[0]["vol"]) == 1000.0
    assert summary["fields"]["open"]["selected"] == "open_adj"
    assert summary["fields"]["cap"]["selected"] == "circ_mv"


def test_build_dolphindb_input_records_fallbacks() -> None:
    panel = _panel().drop(
        columns=[
            "open_adj",
            "high_adj",
            "low_adj",
            "close_adj",
            "vwap_adj",
            "volume",
            "circ_mv",
            "industry",
        ]
    )
    panel["vol"] = [10.0, 11.0]
    panel["total_mv"] = [9000.0, 9100.0]

    ddb_input, summary = build_dolphindb_input(panel, ["alpha101"])

    assert float(ddb_input.iloc[0]["open"]) == 10.0
    assert float(ddb_input.iloc[0]["vol"]) == 1000.0
    assert ddb_input.iloc[0]["indclass"] == "UNKNOWN"
    assert "open" in summary["fallback_fields"]
    assert "vol" in summary["fallback_fields"]
    assert "indclass" in summary["missing_optional_fields"]


def test_alpha191_requires_benchmark_open_and_close() -> None:
    panel = _panel().drop(columns=["benchmark_open"])

    with pytest.raises(ExternalAlphaInputError, match="index_open"):
        build_dolphindb_input(panel, ["alpha191"])


def test_duplicate_date_ticker_keys_are_rejected() -> None:
    panel = _panel()
    duplicate = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)

    with pytest.raises(ExternalAlphaValidationError, match="duplicate date/ticker"):
        validate_date_ticker_keys(duplicate, source_name="input panel")


def test_external_alpha_column_validation_rejects_missing_and_unexpected_columns() -> None:
    alpha = _alpha_output("alpha101").drop(columns=["alpha101_101"])
    with pytest.raises(ExternalAlphaValidationError, match="missing columns"):
        validate_external_alpha_columns(alpha, ["alpha101"])

    alpha = _alpha_output("alpha101")
    alpha["alpha191_001"] = 1.0
    with pytest.raises(ExternalAlphaValidationError, match="unexpected alpha columns"):
        validate_external_alpha_columns(alpha, ["alpha101"])


def test_merge_external_alpha_columns_preserves_panel_shape() -> None:
    panel = _panel().set_index(["date", "ticker"])
    alpha = _alpha_output("alpha101", _panel(), value=0.5)

    merged, validation = merge_external_alpha_columns(panel, alpha, ["alpha101"])

    assert len(merged) == len(panel)
    assert "alpha101_001" in merged.columns
    assert "alpha101_101" in merged.columns
    assert validation["input_rows"] == len(panel)
    assert validation["matched_external_rows"] == len(panel)


def test_merge_external_alpha_columns_rejects_extra_result_keys() -> None:
    panel = _panel().iloc[[0]]
    alpha = _alpha_output("alpha101", _panel(), value=0.5)

    with pytest.raises(ExternalAlphaValidationError, match="keys outside"):
        merge_external_alpha_columns(panel, alpha, ["alpha101"])


def test_external_alpha_manifest_records_provenance_and_redacts_secrets(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    panel = _panel()
    merged, validation = merge_external_alpha_columns(panel, _alpha_output("alpha101"), ["alpha101"])
    panel.to_parquet(input_path)
    merged.to_parquet(output_path)
    _, field_mapping = build_dolphindb_input(panel, ["alpha101"])

    manifest = build_external_alpha_manifest(
        input_path=input_path,
        output_path=output_path,
        input_frame=panel,
        output_frame=merged,
        families=["alpha101"],
        field_mapping=field_mapping,
        validation=validation,
        dolphindb={
            "host": "127.0.0.1",
            "port": 8848,
            "user": "admin",
            "password": "supersecret",
            "api_token": "token-value",
        },
        module_versions={"wq101alpha": "test"},
        generated_at_utc="2026-01-01T00:00:00+00:00",
    )

    manifest_text = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    assert manifest["families"] == ["alpha101"]
    assert manifest["output_data"]["sha256"]
    assert not manifest_contains_secret_text(manifest, "supersecret")
    assert "password" not in manifest_text
    assert "api_token" not in manifest_text
