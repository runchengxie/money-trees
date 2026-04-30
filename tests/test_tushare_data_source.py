from __future__ import annotations

import json
import os
import sqlite3

import numpy as np
import pandas as pd
import pytest

from moneytree.cli.tushare import parse_args
from moneytree.data import MarketDataSanityReport
from moneytree.data_quality import DataQualityResult
from moneytree.data_sources.tushare import (
    TushareDailyConfig,
    _call_api,
    _emit_tushare_sanity_report,
    _TushareApiOptions,
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
    assert panel.attrs["is_st_source"] == "tushare_stock_basic_latest_name_flag"
    assert panel.attrs["is_st_point_in_time"] is False


def test_standardize_tushare_cn_daily_panel_deduplicates_suspend_records() -> None:
    suspend = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": ["20210104", "20210104"],
            "suspend_type": ["R", "S"],
        }
    )

    panel = standardize_tushare_cn_daily_panel(
        daily=_daily(),
        benchmark_daily=_benchmark(),
        suspend=suspend,
    )

    assert not panel.index.has_duplicates
    assert bool(panel.loc[(pd.Timestamp("2021-01-04"), "000001.SZ"), "is_suspended"]) is True


def test_standardize_tushare_local_factors_default_to_float32() -> None:
    panel = standardize_tushare_cn_daily_panel(
        daily=_daily(),
        benchmark_daily=_benchmark(),
        factor_families=("alpha158",),
    )

    assert str(panel["alpha158_kmid"].dtype) == "float32"


def test_standardize_tushare_local_factors_can_keep_float64() -> None:
    panel = standardize_tushare_cn_daily_panel(
        daily=_daily(),
        benchmark_daily=_benchmark(),
        factor_families=("alpha158",),
        factor_dtype="float64",
    )

    assert str(panel["alpha158_kmid"].dtype) == "float64"


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


class _ProxyEnvProbePro:
    def __init__(self) -> None:
        self.seen: dict[str, str | None] = {}

    def daily(self, **kwargs) -> pd.DataFrame:
        self.seen = {
            "HTTP_PROXY": os.environ.get("HTTP_PROXY"),
            "HTTPS_PROXY": os.environ.get("HTTPS_PROXY"),
            "ALL_PROXY": os.environ.get("ALL_PROXY"),
            "http_proxy": os.environ.get("http_proxy"),
            "https_proxy": os.environ.get("https_proxy"),
            "all_proxy": os.environ.get("all_proxy"),
            "NO_PROXY": os.environ.get("NO_PROXY"),
            "no_proxy": os.environ.get("no_proxy"),
        }
        return pd.DataFrame({"ok": [1]})


class _ProxyError(RuntimeError):
    pass


class _ProxyFallbackPro:
    def __init__(self) -> None:
        self.http_proxy_values: list[str | None] = []

    def daily(self, **kwargs) -> pd.DataFrame:
        self.http_proxy_values.append(os.environ.get("HTTP_PROXY"))
        if len(self.http_proxy_values) == 1:
            raise _ProxyError("proxy connection failed")
        return pd.DataFrame({"ok": [1]})


class _RateLimitOncePro:
    def __init__(self) -> None:
        self.calls = 0

    def daily(self, **kwargs) -> pd.DataFrame:
        self.calls += 1
        if self.calls == 1:
            raise Exception("抱歉，您访问接口(daily)频率超限(500次/分钟)")
        return pd.DataFrame({"ok": [1]})


def test_call_api_defaults_to_direct_proxy_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    proxy_url = "http://127.0.0.1:10810"
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(name, proxy_url)
    monkeypatch.setenv("NO_PROXY", "localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1")

    pro = _ProxyEnvProbePro()
    _call_api(pro, "daily")

    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        assert pro.seen[name] is None
        assert os.environ[name] == proxy_url
    assert pro.seen["NO_PROXY"] == "localhost,127.0.0.1,api.waditu.com,waditu.com"
    assert pro.seen["no_proxy"] == "localhost,127.0.0.1,api.waditu.com,waditu.com"
    assert os.environ["NO_PROXY"] == "localhost"
    assert os.environ["no_proxy"] == "127.0.0.1"


def test_call_api_proxy_mode_uses_explicit_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    proxy_url = "http://127.0.0.1:10810"
    monkeypatch.setenv("HTTP_PROXY", "http://env-proxy:8080")
    monkeypatch.setenv("NO_PROXY", "api.waditu.com")

    pro = _ProxyEnvProbePro()
    _call_api(
        pro,
        "daily",
        api_options=_TushareApiOptions(proxy_mode="proxy", proxy_url=proxy_url),
    )

    assert pro.seen["HTTP_PROXY"] == proxy_url
    assert pro.seen["HTTPS_PROXY"] == proxy_url
    assert pro.seen["ALL_PROXY"] == proxy_url
    assert pro.seen["NO_PROXY"] is None
    assert os.environ["HTTP_PROXY"] == "http://env-proxy:8080"
    assert os.environ["NO_PROXY"] == "api.waditu.com"


def test_call_api_proxy_error_falls_back_to_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:10810")
    pro = _ProxyFallbackPro()

    with pytest.warns(RuntimeWarning, match="retrying direct"):
        frame = _call_api(
            pro,
            "daily",
            api_options=_TushareApiOptions(proxy_mode="env"),
        )

    assert len(frame) == 1
    assert pro.http_proxy_values == ["http://127.0.0.1:10810", None]
    assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:10810"


def test_call_api_retries_rate_limit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(
        "moneytree.data_sources.tushare.time.sleep",
        lambda seconds: sleeps.append(float(seconds)),
    )
    pro = _RateLimitOncePro()

    with pytest.warns(RuntimeWarning, match="rate limit"):
        frame = _call_api(
            pro,
            "daily",
            api_options=_TushareApiOptions(
                rate_limit_retries=1,
                rate_limit_wait_seconds=0.5,
            ),
        )

    assert len(frame) == 1
    assert pro.calls == 2
    assert sleeps == [0.5]


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


def test_fetch_tushare_cn_daily_panel_reports_progress(
    capsys: pytest.CaptureFixture[str],
) -> None:
    panel = fetch_tushare_cn_daily_panel(
        TushareDailyConfig(
            start_date="20210104",
            end_date="20210105",
            include_daily_basic=False,
            include_adj_factor=False,
            include_limits=False,
            include_suspend=False,
            include_stock_basic=False,
            show_progress=True,
            progress_every=1,
        ),
        pro=_CountingFakePro(),
    )

    captured = capsys.readouterr()

    assert len(panel) == 4
    assert captured.out == ""
    assert "[tushare] trade_dates=2 start=20210104 end=20210105" in captured.err
    assert "[tushare:daily] 1/2 trade_dates rows=2 cache_hits=0 fetched=1" in captured.err
    assert "[tushare:daily] 2/2 trade_dates rows=4 cache_hits=0 fetched=2" in captured.err
    assert "[tushare:standardize] building canonical date,ticker panel" in captured.err
    assert "[tushare:done] rows=4" in captured.err


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
            "--progress",
            "--progress-every",
            "10",
            "--factor-dtype",
            "float64",
            "--sanity-check",
            "error",
            "--row-group-size",
            "1000",
            "--cache-row-group-size",
            "500",
            "--request-interval-seconds",
            "0.2",
            "--rate-limit-retries",
            "7",
            "--rate-limit-wait-seconds",
            "61.5",
        ]
    )

    assert args.cache_dir == "data/raw/tushare"
    assert args.refresh_cache is True
    assert args.refresh_recent_days == 20
    assert args.progress is True
    assert args.progress_every == 10
    assert args.factor_dtype == "float64"
    assert args.sanity_check == "error"
    assert args.row_group_size == 1000
    assert args.cache_row_group_size == 500
    assert args.request_interval_seconds == 0.2
    assert args.rate_limit_retries == 7
    assert args.rate_limit_wait_seconds == 61.5


def test_tushare_cli_accepts_proxy_args() -> None:
    args = parse_args(
        [
            "--start-date",
            "20210104",
            "--end-date",
            "20210105",
            "--output",
            "data/cn_daily.parquet",
            "--proxy-mode",
            "env",
            "--proxy-url",
            "http://127.0.0.1:10810",
            "--no-fallback-direct",
        ]
    )

    assert args.proxy_mode == "env"
    assert args.proxy_url == "http://127.0.0.1:10810"
    assert args.no_fallback_direct is True


def test_tushare_sanity_wrapper_uses_shared_quality_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_quality_result(*args, **kwargs) -> DataQualityResult:
        return DataQualityResult(
            report=MarketDataSanityReport(
                row_count=1,
                column_count=2,
                date_min="2021-01-04",
                date_max="2021-01-04",
                date_count=1,
                ticker_count=1,
                duplicate_key_count=1,
                missing_required_columns=(),
                null_rates={},
                non_positive_price_counts={},
                negative_volume_count=0,
                inverted_ohlc_count=0,
                warnings=(),
                errors=("duplicate date/ticker keys: 1",),
            )
        )

    monkeypatch.setattr(
        "moneytree.data_sources.tushare.build_tushare_panel_quality_result",
        fake_quality_result,
    )

    with pytest.raises(ValueError, match="duplicate date/ticker"):
        _emit_tushare_sanity_report(
            pd.DataFrame({"date": ["20210104"], "ticker": ["000001.SZ"]}),
            stage="base",
            mode="error",
            show_progress=False,
        )
