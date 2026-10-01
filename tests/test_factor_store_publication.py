from __future__ import annotations

import io
import json
import tarfile
from collections import defaultdict

import pandas as pd
import pytest

from moneytree.factors.store_publication import (
    _update_chunk,
    build_factor_evidence_snapshot_from_archive,
    build_factor_evidence_snapshot_from_store,
    build_signal_quality_report,
)


def _write_tar_member(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    archive.addfile(info, io.BytesIO(payload))


def test_store_ic_uses_pairwise_valid_rows_for_sparse_factor() -> None:
    index = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-02"]), ["A", "B", "C", "D"]],
        names=["date", "ticker"],
    )
    factors = pd.DataFrame({"alpha101_001": [1.0, 2.0, 3.0, float("nan")]}, index=index)
    returns = pd.Series([1.0, 2.0, 3.0, 10.0], index=index)
    sums, counts, ic_values, rank_ic_values = (defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(int)), defaultdict(list), defaultdict(list))
    _update_chunk(
        factors, returns, group_count=2, sums=sums, counts=counts,
        ic_values=ic_values, rank_ic_values=rank_ic_values,
        valid_counts=defaultdict(int), total_observations=defaultdict(int),
        dates_seen=set(), tickers_seen=set(),
    )
    assert ic_values["alpha101_001"] == pytest.approx([1.0])
    assert rank_ic_values["alpha101_001"] == pytest.approx([1.0])


def test_store_rank_ic_reranks_returns_on_pairwise_valid_rows() -> None:
    index = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-02"]), ["A", "B", "C", "D"]],
        names=["date", "ticker"],
    )
    factors = pd.DataFrame({"alpha101_001": [1.0, 2.0, 3.0, float("nan")]}, index=index)
    returns = pd.Series([1.0, 3.0, 4.0, 2.0], index=index)
    rank_ic_values = defaultdict(list)
    _update_chunk(
        factors, returns, group_count=2,
        sums=defaultdict(lambda: defaultdict(float)), counts=defaultdict(lambda: defaultdict(int)),
        ic_values=defaultdict(list), rank_ic_values=rank_ic_values,
        valid_counts=defaultdict(int), total_observations=defaultdict(int),
        dates_seen=set(), tickers_seen=set(),
    )
    assert rank_ic_values["alpha101_001"] == pytest.approx([1.0])


def test_factor_store_publication_reads_partitions_without_private_rows(tmp_path) -> None:
    index = pd.MultiIndex.from_product(
        [pd.to_datetime(["2024-01-02", "2024-01-03"]), ["A", "B"]],
        names=["date", "ticker"],
    )
    base = pd.DataFrame(
        {"next_period_return": [0.01, -0.01, 0.02, -0.02]},
        index=index,
    )
    factors = pd.DataFrame({"alpha101_001": [1.0, 2.0, 2.0, 1.0]}, index=index)
    store = tmp_path / "store"
    (store / "factors" / "alpha101").mkdir(parents=True)
    base.to_parquet(store / "base.parquet")
    factors.to_parquet(store / "factors" / "alpha101" / "part-0001.parquet")
    manifest = {
        "manifest_schema_version": "1.0",
        "kind": "moneytree_factor_store",
        "base_panel": {"path": "base.parquet", "rows": 4, "columns": 1},
        "factor_families": {
            "alpha101": {
                "paths": ["factors/alpha101/part-0001.parquet"],
                "parts": [
                    {
                        "path": "factors/alpha101/part-0001.parquet",
                        "start_date": "2024-01-02",
                        "end_date": "2024-01-03",
                        "rows": 4,
                    }
                ],
            }
        },
    }
    manifest_path = store / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    payload = build_factor_evidence_snapshot_from_store(
        manifest_path,
        data_version="hard-drive-factor-store-v1",
        group_count=2,
    )

    assert payload["data_version"] == "hard-drive-factor-store-v1"
    assert payload["dataset"]["observation_count"] == 4
    assert payload["factors"][0]["name"] == "alpha101_001"
    assert payload["factors"][0]["coverage"]["valid_observations"] == 4
    assert payload["schema_version"] == "1.1"
    assert payload["factors"][0]["annual_slices"] == []
    assert payload["factors"][0]["regime_slices"] == []
    assert payload["factors"][0]["uncertainty"]["status"] == "not_provided"
    assert payload["multiple_testing"]["status"] == "not_provided"
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    assert '"ticker"' not in encoded
    assert str(tmp_path) not in encoded


def test_factor_store_publication_reads_unextracted_tar_archive(tmp_path) -> None:
    index = pd.MultiIndex.from_product(
        [pd.to_datetime(["2016-01-04", "2016-01-05"]), ["A", "B"]],
        names=["date", "ticker"],
    )
    base = pd.DataFrame(
        {"next_period_return": [0.01, -0.01, 0.02, -0.02]},
        index=index,
    )
    factors = pd.DataFrame({"alpha101_001": [1.0, 2.0, 2.0, 1.0]}, index=index)
    prefix = "data/factor_store/cn_daily_2016_2025"
    manifest = {
        "manifest_schema_version": "1.0",
        "kind": "moneytree_factor_store",
        "base_panel": {"path": "base.parquet", "rows": 4, "columns": 1},
        "factor_families": {
            "alpha101": {
                "paths": ["factors/alpha101/part-0001.parquet"],
                "parts": [
                    {
                        "path": "factors/alpha101/part-0001.parquet",
                        "start_date": "2016-01-04",
                        "end_date": "2016-01-05",
                        "rows": 4,
                    }
                ],
            }
        },
    }
    base_path = tmp_path / "base.parquet"
    factor_path = tmp_path / "part.parquet"
    base.to_parquet(base_path)
    factors.to_parquet(factor_path)
    archive_path = tmp_path / "factor-store.tar"
    with tarfile.open(archive_path, "w") as archive:
        _write_tar_member(archive, f"{prefix}/manifest.json", json.dumps(manifest).encode())
        _write_tar_member(archive, f"{prefix}/base.parquet", base_path.read_bytes())
        _write_tar_member(
            archive,
            f"{prefix}/factors/alpha101/part-0001.parquet",
            factor_path.read_bytes(),
        )

    payload = build_factor_evidence_snapshot_from_archive(
        archive_path,
        data_version="hard-drive-factor-store-v1",
        group_count=2,
    )

    assert payload["data_version"] == "hard-drive-factor-store-v1"
    assert payload["dataset"]["date_start"] == "2016-01-04"
    assert payload["dataset"]["date_end"] == "2016-01-05"
    assert payload["factors"][0]["name"] == "alpha101_001"
    assert payload["schema_version"] == "1.1"
    assert payload["factors"][0]["annual_slices"] == []
    assert payload["multiple_testing"]["status"] == "not_provided"
    assert '"ticker"' not in json.dumps(payload, ensure_ascii=False)


def test_signal_quality_report_is_aggregate_only() -> None:
    snapshot = {
        "data_version": "test",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "dataset": {"date_start": "2024-01-01", "date_end": "2024-01-02"},
        "factors": [
            {
                "name": "alpha101_001",
                "coverage": {"ratio": 1.0},
                "rank_ic": {"mean": 0.02, "positive_rate": 0.6},
            },
            {
                "name": "alpha101_002",
                "coverage": {"ratio": 0.5},
                "rank_ic": {"mean": None, "positive_rate": None},
            },
        ],
    }
    report = build_signal_quality_report(snapshot)
    assert report["status"] == "warn"
    assert report["summary"]["factor_count"] == 2
    assert report["summary"]["low_coverage_factor_count"] == 1
    encoded = json.dumps(report, ensure_ascii=False)
    assert "alpha101_001" not in encoded
    assert "ticker-level values" in encoded
