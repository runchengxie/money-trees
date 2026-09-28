from __future__ import annotations

import json

import pandas as pd

from moneytree.factors.store_publication import build_factor_evidence_snapshot_from_store


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
