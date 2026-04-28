from __future__ import annotations

import json
import sqlite3

import pandas as pd
import pytest

from moneytree.cli.data_status import main
from moneytree.data import save_market_data
from moneytree.data_status import build_data_status_report
from moneytree.factor_store import write_factor_store


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-04", "2021-01-05"]),
            "ticker": ["000001.SZ", "000001.SZ"],
            "open": [10.0, 10.2],
            "high": [10.3, 10.5],
            "low": [9.8, 10.0],
            "close": [10.1, 10.4],
            "volume": [1000.0, 1100.0],
            "vwap": [10.05, 10.3],
            "next_period_return": [0.01, 0.02],
            "benchmark_cum_ret": [1.0, 1.01],
            "benchmark_next_period_return": [0.0, 0.0],
            "hit_up_limit": [False, False],
            "hit_down_limit": [False, False],
            "is_suspended": [False, False],
            "is_st": [False, False],
            "alpha158_kmid": [0.1, 0.2],
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
        conn.executemany(
            """
            INSERT INTO raw_cache (
                source, api_name, trade_date, path, rows, columns_json,
                request_hash, params_json, schema_hash, content_hash,
                created_at_utc, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "tushare",
                    "daily",
                    "20210104",
                    "daily/trade_date=20210104.parquet",
                    2,
                    "[]",
                    "r1",
                    "{}",
                    "s1",
                    "c1",
                    "now",
                    "now",
                ),
                (
                    "tushare",
                    "daily",
                    "20210105",
                    "daily/trade_date=20210105.parquet",
                    3,
                    "[]",
                    "r2",
                    "{}",
                    "s1",
                    "c2",
                    "now",
                    "now",
                ),
            ],
        )


def test_data_status_reports_panel_raw_cache_factor_store_and_artifacts(tmp_path, capsys) -> None:
    panel_path = tmp_path / "panel.parquet"
    save_market_data(_panel().set_index(["date", "ticker"]), panel_path)
    cache_dir = tmp_path / "raw-cache"
    _write_raw_cache_manifest(cache_dir)
    store_dir = tmp_path / "store"
    write_factor_store(_panel(), store_dir, families=["alpha158"])
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "experiment_manifest.json").write_text("{}", encoding="utf-8")

    exit_code = main(
        [
            "--panel",
            str(panel_path),
            "--raw-cache",
            str(cache_dir),
            "--factor-store",
            str(store_dir),
            "--artifacts",
            str(artifacts_dir),
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "[data-status] status=ok" in out
    assert "[data-status:base_panel] rows=2" in out
    assert "api=tushare.daily" in out
    assert "family=alpha158" in out
    assert "total_size=" in out


def test_data_status_outputs_json(tmp_path, capsys) -> None:
    panel_path = tmp_path / "panel.parquet"
    save_market_data(_panel().set_index(["date", "ticker"]), panel_path)

    exit_code = main(["--panel", str(panel_path), "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["layers"]["base_panel"]["rows"] == 2


def test_data_status_error_mode_fails_on_duplicate_panel_keys(tmp_path) -> None:
    panel_path = tmp_path / "panel.parquet"
    duplicate = pd.concat([_panel(), _panel().iloc[[0]]], ignore_index=True).set_index(
        ["date", "ticker"]
    )
    save_market_data(duplicate, panel_path)

    assert main(["--panel", str(panel_path), "--mode", "warn"]) == 0
    assert main(["--panel", str(panel_path), "--mode", "error"]) == 1


def test_data_status_reports_missing_raw_cache_manifest(tmp_path) -> None:
    report = build_data_status_report(raw_cache=tmp_path / "raw-cache")

    assert not report.ok
    assert "raw cache manifest does not exist" in report.errors[0]


def test_data_status_rejects_missing_layer_arguments() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_data_status_does_not_modify_panel(tmp_path) -> None:
    panel_path = tmp_path / "panel.parquet"
    save_market_data(_panel().set_index(["date", "ticker"]), panel_path)
    before = panel_path.read_bytes()

    assert main(["--panel", str(panel_path)]) == 0

    assert panel_path.read_bytes() == before


def test_data_status_reports_missing_factor_store_file(tmp_path) -> None:
    store_dir = tmp_path / "store"
    manifest = write_factor_store(_panel(), store_dir, families=["alpha158"])
    factor_path = store_dir / manifest["factor_families"]["alpha158"]["path"]
    factor_path.unlink()

    report = build_data_status_report(factor_store=store_dir)

    assert not report.ok
    assert "factor file does not exist" in report.errors[0]
