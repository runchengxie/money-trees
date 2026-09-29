from __future__ import annotations

import json

import pandas as pd

from moneytree.factors.store_publication import (
    build_factor_evidence_snapshot_from_store,
    build_signal_quality_report,
)


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
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    assert '"ticker"' not in encoded
    assert str(tmp_path) not in encoded


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
