from __future__ import annotations

import pandas as pd
import pytest

from moneytree.cli.factor_store import build_parser, run_generation
from moneytree.data import load_market_data
from moneytree.factor_store import (
    FactorStoreValidationError,
    estimate_factor_store_load_memory,
    load_factor_store,
    validate_factor_store_keys,
    write_external_factor_store,
    write_factor_store,
    write_local_factor_store,
    write_local_factor_store_from_parquet,
)
from moneytree.factors.external import external_alpha_columns


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
        row_group_size=1,
    )

    base_path = tmp_path / "store" / "base.parquet"
    factor_path = tmp_path / "store" / "factors" / "alpha158.parquet"

    assert manifest["manifest_schema_version"] == "1.0"
    assert manifest["base_panel"]["path"] == "base.parquet"
    assert manifest["factor_families"]["alpha158"]["path"] == "factors/alpha158.parquet"
    assert manifest["factor_dtype"] == "float32"
    assert manifest["row_group_size"] == 1
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


def test_load_factor_store_can_prune_partitioned_dates(tmp_path) -> None:
    write_local_factor_store(
        _base_panel(days=6),
        tmp_path / "store",
        families=["alpha158"],
        adjusted=False,
        chunk_trade_dates=2,
    )

    out = load_factor_store(
        tmp_path / "store" / "manifest.json",
        include_factor_families=["alpha158"],
        date_start="2021-01-06",
        date_end="2021-01-08",
    )
    estimate = estimate_factor_store_load_memory(
        tmp_path / "store" / "manifest.json",
        include_factor_families=["alpha158"],
        date_start="2021-01-06",
        date_end="2021-01-08",
    )

    loaded_dates = out.index.get_level_values("date")
    assert loaded_dates.min() == pd.Timestamp("2021-01-06")
    assert loaded_dates.max() == pd.Timestamp("2021-01-08")
    assert len(out) == 6
    assert "alpha158_kmid" in out.columns
    assert estimate.rows == 8
    assert estimate.columns >= 158


def test_write_local_factor_store_from_parquet_matches_in_memory_output(tmp_path) -> None:
    input_path = tmp_path / "base.parquet"
    panel = _base_panel(days=8)
    panel.to_parquet(input_path, index=False, row_group_size=4)

    write_local_factor_store(
        panel,
        tmp_path / "memory_store",
        families=["alpha158", "alpha360"],
        adjusted=False,
        chunk_trade_dates=4,
    )
    manifest = write_local_factor_store_from_parquet(
        input_path,
        tmp_path / "stream_store",
        families=["alpha158", "alpha360"],
        adjusted=False,
        chunk_trade_dates=4,
    )

    assert manifest["local_generation"]["input_mode"] == "parquet_streaming"
    memory = load_factor_store(tmp_path / "memory_store" / "manifest.json")
    streamed = load_factor_store(tmp_path / "stream_store" / "manifest.json")
    pd.testing.assert_index_equal(streamed.index, memory.index)
    pd.testing.assert_frame_equal(
        streamed.loc[:, memory.columns],
        memory,
        check_dtype=False,
    )


def test_write_local_factor_store_from_indexed_parquet_reads_date_index(tmp_path) -> None:
    input_path = tmp_path / "base_indexed.parquet"
    _base_panel(days=4).set_index(["date", "ticker"]).to_parquet(
        input_path,
        row_group_size=4,
    )

    manifest = write_local_factor_store_from_parquet(
        input_path,
        tmp_path / "stream_store",
        families=["alpha158"],
        adjusted=False,
        chunk_trade_dates=2,
    )

    assert manifest["base_panel"]["rows"] == 8
    assert manifest["factor_families"]["alpha158"]["rows"] == 8


def test_write_local_factor_store_progress_reports_part_status(tmp_path, capsys) -> None:
    write_local_factor_store(
        _base_panel(days=4),
        tmp_path / "store",
        families=["alpha360"],
        adjusted=False,
        chunk_trade_dates=2,
        show_progress=True,
    )

    err = capsys.readouterr().err
    assert "[factor-store:alpha360] start parts=2" in err
    assert "progress=[" in err
    assert "status=generated" in err
    assert "elapsed=" in err
    assert "eta=" in err
    assert "[factor-store:alpha360] done parts=2 generated=2 skipped=0" in err


def test_write_local_factor_store_skips_existing_partitions(tmp_path) -> None:
    write_local_factor_store(
        _base_panel(days=6),
        tmp_path / "store",
        families=["alpha158"],
        adjusted=False,
        chunk_trade_dates=3,
    )

    manifest = write_local_factor_store(
        _base_panel(days=6),
        tmp_path / "store",
        families=["alpha158"],
        adjusted=False,
        chunk_trade_dates=3,
    )

    assert manifest["local_generation"]["families_generated"] == []
    assert manifest["local_generation"]["families_skipped"] == ["alpha158"]
    assert manifest["local_generation"]["parts_generated"] == {"alpha158": 0}
    assert manifest["local_generation"]["parts_skipped"] == {"alpha158": 2}


def test_write_local_factor_store_incrementally_adds_new_date_partitions(tmp_path) -> None:
    write_local_factor_store(
        _base_panel(days=6),
        tmp_path / "store",
        families=["alpha158"],
        adjusted=False,
        chunk_trade_dates=3,
    )

    manifest = write_local_factor_store(
        _base_panel(days=9),
        tmp_path / "store",
        families=["alpha158"],
        adjusted=False,
        chunk_trade_dates=3,
    )

    entry = manifest["factor_families"]["alpha158"]
    assert len(entry["paths"]) == 3
    assert entry["rows"] == 18
    assert manifest["local_generation"]["families_generated"] == ["alpha158"]
    assert manifest["local_generation"]["families_skipped"] == []
    assert manifest["local_generation"]["parts_generated"] == {"alpha158": 1}
    assert manifest["local_generation"]["parts_skipped"] == {"alpha158": 2}

    out = load_factor_store(tmp_path / "store" / "manifest.json", include_factor_families=["alpha158"])
    assert len(out) == 18
    assert "alpha158_kmid" in out.columns


def test_write_local_factor_store_rejects_base_change_with_unrequested_existing_family(
    tmp_path,
) -> None:
    write_local_factor_store(
        _base_panel(days=6),
        tmp_path / "store",
        families=["alpha158", "alpha360"],
        adjusted=False,
        chunk_trade_dates=3,
    )

    with pytest.raises(FactorStoreValidationError, match="Stale families: alpha360"):
        write_local_factor_store(
            _base_panel(days=9),
            tmp_path / "store",
            families=["alpha158"],
            adjusted=False,
            chunk_trade_dates=3,
        )


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


def test_write_external_factor_store_adds_partitioned_alpha101(tmp_path) -> None:
    base = _base_panel(days=4)
    indexed = base.set_index(["date", "ticker"])
    factors = pd.DataFrame(
        {
            column: float(idx)
            for idx, column in enumerate(external_alpha_columns("alpha101"), start=1)
        },
        index=indexed.index,
    )

    manifest = write_external_factor_store(
        indexed,
        factors,
        tmp_path / "store",
        families=["alpha101"],
        chunk_trade_dates=2,
        metadata={
            "password": "supersecret",
            "dolphindb": {"host": "127.0.0.1", "password": "supersecret"},
        },
    )

    entry = manifest["factor_families"]["alpha101"]
    assert entry["source"] == "dolphindb"
    assert entry["partitioned"] is True
    assert len(entry["paths"]) == 2
    assert entry["rows"] == 8
    assert entry["columns"] == 101
    assert "supersecret" not in (tmp_path / "store" / "manifest.json").read_text(
        encoding="utf-8"
    )

    out = load_factor_store(tmp_path / "store" / "manifest.json", include_factor_families=["alpha101"])
    assert "alpha101_001" in out.columns
    assert str(out["alpha101_001"].dtype) == "float32"


def test_write_external_factor_store_preserves_existing_local_family(tmp_path) -> None:
    base = _base_panel(days=4)
    write_local_factor_store(
        base,
        tmp_path / "store",
        families=["alpha158"],
        adjusted=False,
        chunk_trade_dates=2,
    )
    indexed = base.set_index(["date", "ticker"])
    factors = pd.DataFrame(
        {column: 1.0 for column in external_alpha_columns("alpha101")},
        index=indexed.index,
    )

    manifest = write_external_factor_store(
        indexed,
        factors,
        tmp_path / "store",
        families=["alpha101"],
        chunk_trade_dates=2,
    )

    assert set(manifest["factor_families"]) == {"alpha158", "alpha101"}


def test_write_external_factor_store_rejects_missing_expected_columns(tmp_path) -> None:
    base = _base_panel(days=2).set_index(["date", "ticker"])
    factors = pd.DataFrame(
        {column: 1.0 for column in external_alpha_columns("alpha101")[:-1]},
        index=base.index,
    )

    with pytest.raises(FactorStoreValidationError, match="missing expected columns"):
        write_external_factor_store(
            base,
            factors,
            tmp_path / "store",
            families=["alpha101"],
        )


def test_write_external_factor_store_rejects_existing_base_mismatch(tmp_path) -> None:
    write_local_factor_store(
        _base_panel(days=3),
        tmp_path / "store",
        families=["alpha158"],
        adjusted=False,
        chunk_trade_dates=2,
    )
    base = _base_panel(days=2).set_index(["date", "ticker"])
    factors = pd.DataFrame(
        {column: 1.0 for column in external_alpha_columns("alpha101")},
        index=base.index,
    )

    with pytest.raises(FactorStoreValidationError, match="base panel index does not match"):
        write_external_factor_store(
            base,
            factors,
            tmp_path / "store",
            families=["alpha101"],
        )


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


def test_factor_store_cli_streams_parquet_without_full_panel_load(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "base.parquet"
    _base_panel(days=4).to_parquet(input_path, index=False)

    def _fail_load_market_data(*args, **kwargs):
        raise AssertionError("CLI should stream parquet input")

    monkeypatch.setattr("moneytree.cli.factor_store.load_market_data", _fail_load_market_data)
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
            "2",
        ]
    )

    result = run_generation(args)

    assert result.manifest_path.exists()
    assert result.base_rows == 8
    assert result.factor_families == ("alpha158",)


def test_wide_panel_load_remains_independent_of_factor_store(tmp_path) -> None:
    panel_path = tmp_path / "wide.parquet"
    _panel().to_parquet(panel_path, index=False)

    out = load_market_data(panel_path)

    assert "alpha158_kmid" in out.columns
    assert "alpha360_close_lag00" in out.columns
