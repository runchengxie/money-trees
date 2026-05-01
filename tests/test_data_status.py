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


def _quality_panel() -> pd.DataFrame:
    rows = []
    closes = {
        "000001.SZ": [10.0, 11.0, 12.0],
        "000002.SZ": [20.0, 22.0, 21.0],
    }
    dates = pd.to_datetime(["2021-01-04", "2021-01-05", "2021-01-06"])
    benchmark_close = pd.Series([100.0, 102.0, 101.0], index=dates)
    benchmark_return = benchmark_close.pct_change()
    benchmark_next = benchmark_return.shift(-1)
    for ticker, values in closes.items():
        close = pd.Series(values, index=dates)
        adj_factor = pd.Series([2.0, 2.0, 2.0], index=dates)
        close_adj = close * adj_factor
        return_1d = close_adj.pct_change()
        next_return = return_1d.shift(-1)
        for date in dates:
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "open": close.loc[date],
                    "high": close.loc[date] + 1.0,
                    "low": close.loc[date] - 1.0,
                    "close": close.loc[date],
                    "volume": 1000.0,
                    "vwap": close.loc[date] + 0.1,
                    "adj_factor": adj_factor.loc[date],
                    "open_adj": close.loc[date] * adj_factor.loc[date],
                    "high_adj": (close.loc[date] + 1.0) * adj_factor.loc[date],
                    "low_adj": (close.loc[date] - 1.0) * adj_factor.loc[date],
                    "close_adj": close_adj.loc[date],
                    "vwap_adj": (close.loc[date] + 0.1) * adj_factor.loc[date],
                    "return_1d": return_1d.loc[date],
                    "next_period_return": next_return.loc[date],
                    "benchmark_close": benchmark_close.loc[date],
                    "benchmark_return": benchmark_return.loc[date],
                    "benchmark_next_period_return": benchmark_next.loc[date],
                    "benchmark_cum_ret": (1.0 + benchmark_return.fillna(0.0)).cumprod().loc[date],
                    "hit_up_limit": False,
                    "hit_down_limit": False,
                    "is_suspended": False,
                    "is_st": False,
                }
            )
    return pd.DataFrame(rows).sort_values(["date", "ticker"]).reset_index(drop=True)


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
        records = []
        for api_name in ("daily", "adj_factor", "daily_basic"):
            for trade_date, rows, schema_hash, content_hash in (
                ("20210104", 2, "s1", f"{api_name}-c1"),
                ("20210105", 3, "s1", f"{api_name}-c2"),
            ):
                records.append(
                    (
                        "tushare",
                        api_name,
                        trade_date,
                        f"{api_name}/trade_date={trade_date}.parquet",
                        rows,
                        "[]",
                        f"{api_name}-{trade_date}",
                        "{}",
                        schema_hash,
                        content_hash,
                        "now",
                        "now",
                    )
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
            records,
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
    assert "schema_hashes=" in out
    assert "family=alpha158" in out
    assert "family=alpha158 quality" in out
    assert "total_size=" in out


def test_data_status_outputs_json(tmp_path, capsys) -> None:
    panel_path = tmp_path / "panel.parquet"
    save_market_data(_panel().set_index(["date", "ticker"]), panel_path)

    exit_code = main(["--panel", str(panel_path), "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["layers"]["base_panel"]["rows"] == 2
    assert "null_counts" in payload["layers"]["base_panel"]


def test_data_status_uses_streaming_parquet_panel_check(tmp_path, monkeypatch) -> None:
    panel_path = tmp_path / "panel.parquet"
    save_market_data(_quality_panel().set_index(["date", "ticker"]), panel_path)

    def fail_load_market_data(*args, **kwargs):
        raise AssertionError("parquet status should not load the full frame")

    monkeypatch.setattr("moneytree.data_status.load_market_data", fail_load_market_data)

    report = build_data_status_report(panel=panel_path)

    layer = report.layers["base_panel"]
    assert report.ok
    assert layer["rows"] == 6
    assert layer["date_count"] == 3
    assert layer["ticker_count"] == 2
    assert layer["derived_return_checks"]["return_1d"]["mismatch_count"] == 0
    assert layer["adjusted_price_checks"]["mismatch_counts"]["close_adj"] == 0


def test_data_status_reports_streaming_panel_quality_errors(tmp_path) -> None:
    panel = _quality_panel()
    bad = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)
    bad = bad.sort_values(["date", "ticker"]).reset_index(drop=True)
    bad.loc[0, "open"] = -1.0
    bad.loc[1, "high"] = bad.loc[1, "low"] - 1.0
    bad.loc[2, "volume"] = -100.0
    bad = bad.drop(columns=["is_st"])
    panel_path = tmp_path / "bad.parquet"
    save_market_data(bad.set_index(["date", "ticker"]), panel_path)

    report = build_data_status_report(panel=panel_path)
    layer = report.layers["base_panel"]

    assert not report.ok
    assert layer["duplicate_key_count"] == 1
    assert "is_st" in layer["missing_required_columns"]
    assert layer["non_positive_price_counts"]["open"] == 1
    assert layer["negative_volume_count"] == 1
    assert layer["inverted_ohlc_count"] == 1


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


def test_data_status_reports_raw_cache_empty_related_shards_and_schema_warnings(tmp_path) -> None:
    cache_dir = tmp_path / "raw-cache"
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
                ("tushare", "daily", "20210104", "daily/a.parquet", 2, "[]", "r1", "{}", "s1", "c1", "now", "now"),
                ("tushare", "daily", "20210105", "daily/b.parquet", 3, "[]", "r2", "{}", "s2", "c2", "now", "now"),
                ("tushare", "adj_factor", "20210104", "adj/a.parquet", 0, "[]", "r3", "{}", "s1", "c3", "now", "now"),
                ("tushare", "daily_basic", "20210104", "basic/a.parquet", 0, "[]", "r4", "{}", "s1", "c4", "now", "now"),
                ("tushare", "adj_factor", "20210105", "adj/b.parquet", 3, "[]", "r5", "{}", "s1", "c5", "now", "now"),
                ("tushare", "daily_basic", "20210105", "basic/b.parquet", 3, "[]", "r6", "{}", "s1", "c6", "now", "now"),
            ],
        )

    report = build_data_status_report(raw_cache=cache_dir)

    assert not report.ok
    assert any("adj_factor has zero rows" in error for error in report.errors)
    assert any("daily_basic has zero rows" in error for error in report.errors)
    assert any("distinct schema hashes" in warning for warning in report.warnings)


def test_data_status_reports_derived_return_and_adjusted_price_mismatches(tmp_path) -> None:
    panel = _quality_panel()
    panel.loc[panel["ticker"] == "000001.SZ", "return_1d"] = 0.0
    panel.loc[0, "next_period_return"] = pd.NA
    panel.loc[1, "close_adj"] = panel.loc[1, "close_adj"] + 1.0
    panel_path = tmp_path / "bad_returns.parquet"
    save_market_data(panel.set_index(["date", "ticker"]), panel_path)

    report = build_data_status_report(panel=panel_path)
    layer = report.layers["base_panel"]

    assert not report.ok
    assert layer["derived_return_checks"]["return_1d"]["mismatch_count"] > 0
    assert layer["derived_return_checks"]["next_period_return"]["unexpected_null_count"] > 0
    assert layer["adjusted_price_checks"]["mismatch_counts"]["close_adj"] == 1


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


def test_data_status_reports_factor_store_value_quality_errors(tmp_path) -> None:
    store_dir = tmp_path / "store"
    panel = _panel()
    panel["alpha158_inf"] = [1.0, 2.0]
    panel["alpha158_all_null"] = [1.0, 2.0]
    panel["alpha158_constant"] = [3.0, 3.0]
    manifest = write_factor_store(panel, store_dir, families=["alpha158"])
    factor_path = store_dir / manifest["factor_families"]["alpha158"]["path"]
    factors = pd.read_parquet(factor_path)
    factors.loc[factors.index[0], "alpha158_inf"] = float("inf")
    factors["alpha158_all_null"] = pd.NA
    factors.to_parquet(factor_path, index=True)

    report = build_data_status_report(factor_store=store_dir)
    quality = report.layers["factor_store"]["factor_families"]["alpha158"]["quality"]

    assert not report.ok
    assert quality["inf_count"] == 1
    assert quality["all_null_column_count"] == 1
    assert quality["constant_column_count"] == 1
    assert any("infinite factor values" in error for error in report.errors)
    assert any("all-null factor columns" in error for error in report.errors)
    assert any("constant factor columns" in warning for warning in report.warnings)
    lines = "\n".join(report.to_lines())
    assert "all_null_columns=alpha158_all_null" in lines
    assert "constant_columns=alpha158_constant" in lines


def test_data_status_allows_known_factor_quality_columns(tmp_path) -> None:
    store_dir = tmp_path / "store"
    panel = _panel()
    panel["alpha158_all_null"] = [1.0, 2.0]
    manifest = write_factor_store(panel, store_dir, families=["alpha158"])
    factor_path = store_dir / manifest["factor_families"]["alpha158"]["path"]
    factors = pd.read_parquet(factor_path)
    factors["alpha158_all_null"] = pd.NA
    factors.to_parquet(factor_path, index=True)

    report = build_data_status_report(factor_store=store_dir)
    allowed = build_data_status_report(
        factor_store=store_dir,
        allowed_factor_columns={"alpha158_all_null"},
    )

    assert not report.ok
    assert allowed.ok
    quality = allowed.layers["factor_store"]["factor_families"]["alpha158"]["quality"]
    assert quality["all_null_column_count"] == 0
    assert quality["allowed_all_null_columns"] == ["alpha158_all_null"]
    assert "allowed_all_null_columns=alpha158_all_null" in "\n".join(allowed.to_lines())


def test_data_status_filters_factor_families_and_can_skip_quality(tmp_path) -> None:
    store_dir = tmp_path / "store"
    panel = _panel()
    panel["alpha360_close_lag00"] = [0.0, 0.0]
    write_factor_store(panel, store_dir, families=["alpha158", "alpha360"])

    report = build_data_status_report(
        factor_store=store_dir,
        factor_families={"alpha360"},
        check_factor_quality=False,
    )

    families = report.layers["factor_store"]["factor_families"]
    assert list(families) == ["alpha360"]
    assert families["alpha360"]["quality"]["checked"] is False
