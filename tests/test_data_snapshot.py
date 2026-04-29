from __future__ import annotations

import json
import sqlite3

import pandas as pd

from moneytree.cli.data_snapshot import main
from moneytree.data import save_market_data
from moneytree.data_snapshot import create_data_snapshot
from moneytree.factor_store import write_factor_store


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-04", "2021-01-05", "2021-01-05"]),
            "ticker": ["000001.SZ", "000001.SZ", "000002.SZ"],
            "open": [10.0, 10.2, 20.0],
            "high": [10.3, 10.5, 20.5],
            "low": [9.8, 10.0, 19.8],
            "close": [10.1, 10.4, 20.1],
            "volume": [1000.0, 1100.0, 2100.0],
            "vwap": [10.05, 10.3, 20.0],
            "next_period_return": [0.01, 0.02, 0.03],
            "benchmark_cum_ret": [1.0, 1.01, 1.01],
            "benchmark_next_period_return": [0.0, 0.0, 0.0],
            "hit_up_limit": [False, False, False],
            "hit_down_limit": [False, False, False],
            "is_suspended": [False, False, False],
            "is_st": [False, False, False],
            "alpha158_kmid": [0.1, 0.2, 0.3],
        }
    )


def _write_raw_cache_manifest(cache_dir) -> None:
    cache_dir.mkdir()
    with sqlite3.connect(cache_dir / "manifest.sqlite") as conn:
        conn.execute(
            """
            CREATE TABLE raw_cache (
                source TEXT NOT NULL,
                api_name TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                path TEXT NOT NULL,
                rows INTEGER NOT NULL,
                columns_json TEXT NOT NULL,
                request_hash TEXT NOT NULL DEFAULT '',
                params_json TEXT NOT NULL DEFAULT '{}',
                schema_hash TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL DEFAULT '',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (source, api_name, trade_date)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO raw_cache (
                source, api_name, trade_date, path, rows, columns_json,
                request_hash, params_json, schema_hash, content_hash,
                created_at_utc, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tushare",
                "daily",
                "20210104",
                "daily/trade_date=20210104.parquet",
                3,
                "[]",
                "r1",
                "{}",
                "s1",
                "c1",
                "now",
                "now",
            ),
        )


def test_create_data_snapshot_writes_metadata_checksums_and_readme(tmp_path) -> None:
    panel_path = tmp_path / "panel.parquet"
    save_market_data(_panel().set_index(["date", "ticker"]), panel_path)
    cache_dir = tmp_path / "raw-cache"
    _write_raw_cache_manifest(cache_dir)
    store_dir = tmp_path / "store"
    write_factor_store(_panel(), store_dir, families=["alpha158"])

    result = create_data_snapshot(
        panel=panel_path,
        output_dir=tmp_path / "snapshot",
        raw_cache=cache_dir,
        factor_store=store_dir,
        label="unit-test",
        notes=["small test panel"],
    )

    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "moneytree_data_snapshot"
    assert payload["label"] == "unit-test"
    assert payload["panel"]["rows"] == 3
    assert payload["panel"]["columns"] >= 16
    assert payload["panel"]["date_min"] == "2021-01-04"
    assert payload["panel"]["date_max"] == "2021-01-05"
    assert payload["panel"]["date_count"] == 2
    assert payload["panel"]["ticker_count"] == 2
    assert payload["panel"]["sha256"]
    assert payload["panel"]["schema_hash"]
    assert payload["references"]["raw_cache"]["manifest_exists"] is True
    assert payload["references"]["factor_store"]["manifest_exists"] is True
    assert "panel.parquet" in result.checksums_path.read_text(encoding="utf-8")
    assert "records metadata and checksums only" in result.readme_path.read_text(encoding="utf-8")


def test_data_snapshot_cli_outputs_json(tmp_path, capsys) -> None:
    panel_path = tmp_path / "panel.parquet"
    save_market_data(_panel().set_index(["date", "ticker"]), panel_path)

    exit_code = main(
        [
            "--panel",
            str(panel_path),
            "--output-dir",
            str(tmp_path / "snapshot"),
            "--format",
            "json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["panel"]["rows"] == 3
    assert (tmp_path / "snapshot" / "dataset_meta.json").exists()


def test_data_snapshot_cli_reports_missing_panel(tmp_path, capsys) -> None:
    exit_code = main(
        [
            "--panel",
            str(tmp_path / "missing.parquet"),
            "--output-dir",
            str(tmp_path / "snapshot"),
        ]
    )

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "panel path does not exist" in err
