from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

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


def test_fetch_tushare_cn_daily_panel_accepts_injected_client() -> None:
    panel = fetch_tushare_cn_daily_panel(
        TushareDailyConfig(start_date="20210104", end_date="20210105"),
        pro=_FakePro(),
    )

    assert len(panel) == 4
    assert "benchmark_cum_ret" in panel.columns
