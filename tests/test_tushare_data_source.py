from __future__ import annotations

import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from moneytree.cli.tushare import parse_args
from moneytree.data_sources.tushare import (
    TushareDailyConfig,
    fetch_tushare_cn_daily_panel,
    resolve_tushare_token,
    standardize_tushare_cn_daily_panel,
)


def _daily() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ", "000001.SZ", "000002.SZ"],
            "trade_date": ["20210104", "20210104", "20210105", "20210105"],
            "open": [10.0, 20.0, 10.2, 19.8],
            "high": [10.5, 20.5, 10.4, 20.1],
            "low": [9.8, 19.5, 10.0, 19.2],
            "close": [10.1, 20.1, 10.3, 19.4],
            "pre_close": [10.0, 20.0, 10.1, 20.1],
            "change": [0.1, 0.1, 0.2, -0.7],
            "pct_chg": [1.0, 0.5, 1.98, -3.48],
            "vol": [100.0, 200.0, 150.0, 250.0],
            "amount": [101.0, 402.0, 154.5, 485.0],
        }
    )


def _benchmark() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["000300.SH", "000300.SH"],
            "trade_date": ["20210104", "20210105"],
            "open": [5000.0, 5010.0],
            "high": [5020.0, 5030.0],
            "low": [4990.0, 5000.0],
            "close": [5010.0, 5020.0],
        }
    )


def test_standardize_tushare_cn_daily_panel_builds_contract() -> None:
    daily_basic = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "trade_date": ["20210104", "20210104"],
            "total_mv": [1000.0, 2000.0],
            "circ_mv": [900.0, 1800.0],
        }
    )
    adj_factor = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ", "000001.SZ", "000002.SZ"],
            "trade_date": ["20210104", "20210104", "20210105", "20210105"],
            "adj_factor": [2.0, 1.0, 2.0, 1.0],
        }
    )
    limits = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "trade_date": ["20210105", "20210105"],
            "up_limit": [10.3, 21.0],
            "down_limit": [9.0, 19.4],
        }
    )
    stock_basic = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "name": ["平安银行", "*ST示例"],
            "list_date": ["19910403", "20200101"],
        }
    )

    panel = standardize_tushare_cn_daily_panel(
        daily=_daily(),
        benchmark_daily=_benchmark(),
        daily_basic=daily_basic,
        adj_factor=adj_factor,
        limits=limits,
        stock_basic=stock_basic,
    )

    idx = (pd.Timestamp("2021-01-04"), "000001.SZ")
    assert np.isclose(float(panel.loc[idx, "volume"]), 10000.0)
    assert np.isclose(float(panel.loc[idx, "vwap"]), 10.1)
    assert np.isclose(float(panel.loc[idx, "close_adj"]), 20.2)
    assert "next_period_return" in panel.columns
    assert "benchmark_next_period_return" in panel.columns
    assert bool(panel.loc[(pd.Timestamp("2021-01-05"), "000001.SZ"), "hit_up_limit"]) is True
    assert bool(panel.loc[(pd.Timestamp("2021-01-05"), "000002.SZ"), "hit_down_limit"]) is True
    assert bool(panel.loc[(pd.Timestamp("2021-01-04"), "000002.SZ"), "is_st"]) is True


def test_resolve_tushare_token_reads_env_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("TUSHARE_TOKEN=abc123\n", encoding="utf-8")

    assert resolve_tushare_token(env_file=env_path) == "abc123"


class _FakePro:
    def trade_cal(self, **kwargs) -> pd.DataFrame:
        return pd.DataFrame({"cal_date": ["20210104", "20210105"], "is_open": [1, 1]})

    def daily(self, **kwargs) -> pd.DataFrame:
        return _daily().loc[_daily()["trade_date"] == kwargs["trade_date"]]

    def index_daily(self, **kwargs) -> pd.DataFrame:
        return _benchmark()

    def daily_basic(self, **kwargs) -> pd.DataFrame:
        return pd.DataFrame(columns=["ts_code", "trade_date"])

    def adj_factor(self, **kwargs) -> pd.DataFrame:
        return pd.DataFrame(columns=["ts_code", "trade_date", "adj_factor"])

    def stk_limit(self, **kwargs) -> pd.DataFrame:
        return pd.DataFrame(columns=["ts_code", "trade_date", "up_limit", "down_limit"])

    def suspend_d(self, **kwargs) -> pd.DataFrame:
        return pd.DataFrame(columns=["ts_code", "trade_date"])

    def stock_basic(self, **kwargs) -> pd.DataFrame:
        return pd.DataFrame(columns=["ts_code", "name", "list_date"])


class _CountingFakePro(_FakePro):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def _record(self, api_name: str, kwargs) -> None:
        self.calls.append((api_name, kwargs.get("trade_date")))

    def daily(self, **kwargs) -> pd.DataFrame:
        self._record("daily", kwargs)
        return super().daily(**kwargs)

    def daily_basic(self, **kwargs) -> pd.DataFrame:
        self._record("daily_basic", kwargs)
        return super().daily_basic(**kwargs)

    def adj_factor(self, **kwargs) -> pd.DataFrame:
        self._record("adj_factor", kwargs)
        return super().adj_factor(**kwargs)

    def stk_limit(self, **kwargs) -> pd.DataFrame:
        self._record("stk_limit", kwargs)
        return super().stk_limit(**kwargs)

    def suspend_d(self, **kwargs) -> pd.DataFrame:
        self._record("suspend_d", kwargs)
        return super().suspend_d(**kwargs)


def test_fetch_tushare_cn_daily_panel_accepts_injected_client() -> None:
    panel = fetch_tushare_cn_daily_panel(
        TushareDailyConfig(start_date="20210104", end_date="20210105"),
        pro=_FakePro(),
    )

    assert len(panel) == 4
    assert "benchmark_cum_ret" in panel.columns


def test_fetch_tushare_cn_daily_panel_uses_trade_date_cache(tmp_path) -> None:
    config = TushareDailyConfig(
        start_date="20210104",
        end_date="20210105",
        cache_dir=tmp_path / "raw-cache",
    )

    first_client = _CountingFakePro()
    first_panel = fetch_tushare_cn_daily_panel(config, pro=first_client)

    assert (tmp_path / "raw-cache" / "daily" / "trade_date=20210104.parquet").exists()
    assert (tmp_path / "raw-cache" / "adj_factor" / "trade_date=20210105.parquet").exists()
    assert ("daily", "20210104") in first_client.calls
    with sqlite3.connect(tmp_path / "raw-cache" / "manifest.sqlite") as conn:
        manifest_row = conn.execute(
            """
            SELECT rows, path, columns_json, request_hash, params_json, schema_hash,
                   content_hash, created_at_utc, updated_at_utc
            FROM raw_cache
            WHERE source = 'tushare' AND api_name = 'daily' AND trade_date = '20210104'
            """
        ).fetchone()
    assert manifest_row is not None
    assert manifest_row[0] == 2
    assert manifest_row[1] == "daily/trade_date=20210104.parquet"
    assert "ts_code" in manifest_row[2]
    assert len(manifest_row[3]) == 64
    params = json.loads(manifest_row[4])
    assert params["source"] == "tushare"
    assert params["api_name"] == "daily"
    assert params["params"]["trade_date"] == "20210104"
    assert len(manifest_row[5]) == 64
    assert len(manifest_row[6]) == 64
    assert manifest_row[7]
    assert manifest_row[8]

    second_client = _CountingFakePro()
    second_panel = fetch_tushare_cn_daily_panel(config, pro=second_client)

    cached_apis = {"daily", "daily_basic", "adj_factor", "stk_limit", "suspend_d"}
    assert [call for call in second_client.calls if call[0] in cached_apis] == []
    pd.testing.assert_frame_equal(first_panel, second_panel)


def test_fetch_tushare_cn_daily_panel_refreshes_recent_cached_dates(tmp_path) -> None:
    base_config = TushareDailyConfig(
        start_date="20210104",
        end_date="20210105",
        cache_dir=tmp_path / "raw-cache",
        include_daily_basic=False,
        include_adj_factor=False,
        include_limits=False,
        include_suspend=False,
        include_stock_basic=False,
    )
    fetch_tushare_cn_daily_panel(base_config, pro=_CountingFakePro())

    refresh_client = _CountingFakePro()
    fetch_tushare_cn_daily_panel(
        TushareDailyConfig(
            start_date="20210104",
            end_date="20210105",
            cache_dir=tmp_path / "raw-cache",
            refresh_recent_days=1,
            include_daily_basic=False,
            include_adj_factor=False,
            include_limits=False,
            include_suspend=False,
            include_stock_basic=False,
        ),
        pro=refresh_client,
    )

    assert refresh_client.calls == [("daily", "20210105")]


def test_fetch_tushare_cn_daily_panel_upgrades_legacy_manifest_schema(tmp_path) -> None:
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
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (source, api_name, trade_date)
            )
            """
        )

    fetch_tushare_cn_daily_panel(
        TushareDailyConfig(
            start_date="20210104",
            end_date="20210105",
            cache_dir=cache_dir,
            include_daily_basic=False,
            include_adj_factor=False,
            include_limits=False,
            include_suspend=False,
            include_stock_basic=False,
        ),
        pro=_CountingFakePro(),
    )

    with sqlite3.connect(cache_dir / "manifest.sqlite") as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(raw_cache)").fetchall()}

    assert {"request_hash", "params_json", "schema_hash", "content_hash", "updated_at_utc"}.issubset(
        columns
    )


def test_tushare_cli_accepts_cache_args() -> None:
    args = parse_args(
        [
            "--start-date",
            "20210104",
            "--end-date",
            "20210105",
            "--output",
            "data/cn_daily.parquet",
            "--cache-dir",
            "data/raw/tushare",
            "--refresh-cache",
            "--refresh-recent-days",
            "20",
        ]
    )

    assert args.cache_dir == "data/raw/tushare"
    assert args.refresh_cache is True
    assert args.refresh_recent_days == 20
