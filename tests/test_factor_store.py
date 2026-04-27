from __future__ import annotations

import pandas as pd
import pytest

from moneytree.data import load_market_data
from moneytree.cli.factor_store import build_parser, run_generation
from moneytree.factor_store import (
    FactorStoreValidationError,
    load_factor_store,
    validate_factor_store_keys,
    write_factor_store,
    write_local_factor_store,
)


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-04", "2021-01-05"]),
            "ticker": ["000001.SZ", "000001.SZ"],
            "close": [10.0, 10.2],
            "next_period_return": [0.01, 0.02],
            "benchmark_next_period_return": [0.0, 0.0],
            "alpha158_kmid": [0.1, 0.2],
            "alpha360_close_lag00": [0.0, 0.0],
        }
    )


def _base_panel(days: int = 30) -> pd.DataFrame:
    dates = pd.date_range("2021-01-04", periods=days, freq="B")
    rows: list[dict[str, object]] = []
    for i, date in enumerate(dates):
        for j, ticker in enumerate(["000001.SZ", "000002.SZ"]):
            base = 10.0 + i * 0.1 + j
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "open": base,
                    "high": base + 0.3,
                    "low": base - 0.2,
                    "close": base + 0.1,
                    "vwap": base + 0.05,
                    "volume": 1000.0 + i * 10.0 + j,
                    "amount": (1000.0 + i * 10.0 + j) * (base + 0.05),
                    "next_period_return": 0.001,
                    "benchmark_next_period_return": 0.0,
                }
            )
    return pd.DataFrame(rows)


def test_write_factor_store_creates_manifest_and_family_files(tmp_path) -> None:
    manifest = write_factor_store(
        _panel(),
        tmp_path / "store",
        families=["alpha158"],
        factor_dtype="float32",
        metadata={"source": "test"},
    )

    base_path = tmp_path / "store" / "base.parquet"
    factor_path = tmp_path / "store" / "factors" / "alpha158.parquet"

    assert manifest["manifest_schema_version"] == "1.0"
    assert manifest["base_panel"]["path"] == "base.parquet"
    assert manifest["factor_families"]["alpha158"]["path"] == "factors/alpha158.parquet"
    assert manifest["factor_dtype"] == "float32"
    assert manifest["metadata"]["source"] == "test"
    assert (tmp_path / "store" / "manifest.json").exists()
    assert base_path.exists()
    assert factor_path.exists()

    base = pd.read_parquet(base_path)
    factors = pd.read_parquet(factor_path)
    assert "alpha158_kmid" not in base.columns
    assert str(factors["alpha158_kmid"].dtype) == "float32"


def test_validate_factor_store_keys_rejects_misaligned_factors() -> None:
    base = _panel().drop(columns=["alpha158_kmid", "alpha360_close_lag00"])
    factors = _panel().loc[[0], ["date", "ticker", "alpha158_kmid"]]

    with pytest.raises(FactorStoreValidationError, match="not aligned"):
        validate_factor_store_keys(base, {"alpha158": factors})


def test_load_factor_store_joins_only_requested_families(tmp_path) -> None:
    write_factor_store(_panel(), tmp_path / "store")

    out = load_factor_store(
        tmp_path / "store" / "manifest.json",
        include_factor_families=["alpha158"],
    )

    assert "close" in out.columns
    assert "alpha158_kmid" in out.columns
    assert "alpha360_close_lag00" not in out.columns
    assert out.index.names == ["date", "ticker"]


def test_write_local_factor_store_generates_partitioned_family(tmp_path) -> None:
    manifest = write_local_factor_store(
        _base_panel(),
        tmp_path / "store",
        families=["alpha158"],
        adjusted=False,
        chunk_trade_dates=10,
    )

    entry = manifest["factor_families"]["alpha158"]
    assert entry["partitioned"] is True
    assert len(entry["paths"]) == 3
    assert entry["rows"] == 60
    assert entry["columns"] == 158
    assert (tmp_path / "store" / "base.parquet").exists()
    assert (tmp_path / "store" / entry["paths"][0]).exists()

    out = load_factor_store(tmp_path / "store" / "manifest.json", include_factor_families=["alpha158"])

    assert len(out) == 60
    assert "open" in out.columns
    assert "alpha158_kmid" in out.columns
    assert str(out["alpha158_kmid"].dtype) == "float32"


def test_write_local_factor_store_can_add_missing_family_incrementally(tmp_path) -> None:
    write_local_factor_store(
        _base_panel(days=12),
        tmp_path / "store",
        families=["alpha158"],
        adjusted=False,
        chunk_trade_dates=6,
    )

    manifest = write_local_factor_store(
        _base_panel(days=12),
        tmp_path / "store",
        families=["alpha158", "alpha360"],
        adjusted=False,
        chunk_trade_dates=6,
    )

    assert set(manifest["factor_families"]) == {"alpha158", "alpha360"}
    assert manifest["local_generation"]["families_skipped"] == ["alpha158"]
    assert manifest["local_generation"]["families_generated"] == ["alpha360"]


def test_factor_store_cli_generates_local_store(tmp_path) -> None:
    input_path = tmp_path / "base.parquet"
    _base_panel(days=8).to_parquet(input_path, index=False)

    args = build_parser().parse_args(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "store"),
            "--factor-family",
            "alpha158",
            "--raw-features",
            "--chunk-trade-dates",
            "4",
        ]
    )
    result = run_generation(args)

    assert result.manifest_path.exists()
    assert result.base_rows == 16
    assert result.factor_families == ("alpha158",)


def test_wide_panel_load_remains_independent_of_factor_store(tmp_path) -> None:
    panel_path = tmp_path / "wide.parquet"
    _panel().to_parquet(panel_path, index=False)

    out = load_market_data(panel_path)

    assert "alpha158_kmid" in out.columns
    assert "alpha360_close_lag00" in out.columns
