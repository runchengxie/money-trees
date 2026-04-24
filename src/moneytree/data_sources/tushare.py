from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from moneytree.data import ensure_date_ticker_index
from moneytree.factors import add_factor_family_features


TOKEN_ENV_NAMES = ("TUSHARE_TOKEN", "TUSHARE_PRO_TOKEN", "TS_TOKEN", "TUSHARE_API_KEY")


@dataclass(frozen=True)
class TushareDailyConfig:
    start_date: str
    end_date: str
    benchmark: str = "000300.SH"
    tickers: tuple[str, ...] = ()
    factor_families: tuple[str, ...] = ()
    env_file: str | Path = ".env"
    token: str | None = None
    include_daily_basic: bool = True
    include_adj_factor: bool = True
    include_limits: bool = True
    include_suspend: bool = True
    include_stock_basic: bool = True
    complete_calendar: bool = False
    adjusted_features: bool = True
    extra_query_kwargs: dict[str, Any] = field(default_factory=dict)


def _parse_env_file(path: str | Path) -> dict[str, str]:
    file_path = Path(path)
    if not file_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def resolve_tushare_token(
    token: str | None = None,
    *,
    env_file: str | Path | None = ".env",
) -> str:
    """Resolve a TuShare token from explicit input, environment, or a local env file."""
    if token:
        return token

    for name in TOKEN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value

    env_values = _parse_env_file(env_file) if env_file else {}
    for name in TOKEN_ENV_NAMES:
        value = env_values.get(name)
        if value:
            return value

    names = ", ".join(TOKEN_ENV_NAMES)
    raise RuntimeError(f"Missing TuShare token. Set one of: {names}.")


def create_tushare_client(token: str | None = None, *, env_file: str | Path | None = ".env"):
    resolved = resolve_tushare_token(token, env_file=env_file)
    try:
        import tushare as ts
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "TuShare support requires the optional tushare dependency. "
            "Install it with the project's tushare extra."
        ) from exc
    ts.set_token(resolved)
    return ts.pro_api(resolved)


def _normalize_date_str(value: str) -> str:
    text = str(value).strip()
    return text.replace("-", "")


def _to_datetime_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype(str), format="%Y%m%d", errors="coerce")


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if frame is not None and not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    return pd.concat(non_empty, ignore_index=True).drop_duplicates()


def _call_api(pro, api_name: str, **params) -> pd.DataFrame:
    method = getattr(pro, api_name)
    clean_params = {key: value for key, value in params.items() if value is not None}
    out = method(**clean_params)
    return out if isinstance(out, pd.DataFrame) else pd.DataFrame(out)


def _fetch_trade_dates(pro, start_date: str, end_date: str) -> list[str]:
    start = _normalize_date_str(start_date)
    end = _normalize_date_str(end_date)
    try:
        calendar = _call_api(
            pro,
            "trade_cal",
            exchange="",
            start_date=start,
            end_date=end,
            is_open="1",
        )
    except Exception:
        calendar = pd.DataFrame()

    if not calendar.empty and "cal_date" in calendar.columns:
        if "is_open" in calendar.columns:
            mask = calendar["is_open"].astype(str) == "1"
        else:
            mask = pd.Series(True, index=calendar.index)
        dates = calendar.loc[mask, "cal_date"]
        return sorted(str(value) for value in dates.dropna().unique())

    fallback = pd.bdate_range(pd.to_datetime(start), pd.to_datetime(end))
    return [date.strftime("%Y%m%d") for date in fallback]


def _filter_tickers(frame: pd.DataFrame, tickers: tuple[str, ...]) -> pd.DataFrame:
    if frame.empty or not tickers or "ts_code" not in frame.columns:
        return frame
    return frame.loc[frame["ts_code"].isin(tickers)].copy()


def _fetch_by_trade_date(
    pro,
    api_name: str,
    trade_dates: list[str],
    *,
    tickers: tuple[str, ...] = (),
    fields: str | None = None,
    **extra_params,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for trade_date in trade_dates:
        frame = _call_api(
            pro,
            api_name,
            trade_date=trade_date,
            fields=fields,
            **extra_params,
        )
        frames.append(_filter_tickers(frame, tickers))
    return _concat(frames)


def _standardize_daily(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        raise ValueError("TuShare daily data is empty.")
    required = {"ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"}
    missing = required.difference(daily.columns)
    if missing:
        raise KeyError(f"Missing TuShare daily columns: {sorted(missing)}")

    out = daily.copy()
    out["date"] = _to_datetime_date(out["trade_date"])
    out["ticker"] = out["ts_code"].astype(str)
    out["volume"] = out["vol"].astype(float) * 100.0
    denom = out["volume"].replace(0, np.nan)
    out["vwap"] = out["amount"].astype(float) * 1000.0 / denom
    out = out.drop(columns=["ts_code", "trade_date"])
    return ensure_date_ticker_index(out)


def _normalize_merge_frame(frame: pd.DataFrame, date_col: str = "trade_date") -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "ticker"])
    if "ts_code" not in frame.columns:
        return pd.DataFrame(columns=["date", "ticker"])
    out = frame.copy()
    if date_col not in out.columns:
        return pd.DataFrame(columns=["date", "ticker"])
    out["date"] = _to_datetime_date(out[date_col])
    out["ticker"] = out["ts_code"].astype(str)
    out = out.drop(columns=[col for col in ("ts_code", date_col) if col in out.columns])
    return ensure_date_ticker_index(out)


def _merge_optional(panel: pd.DataFrame, frame: pd.DataFrame | None, date_col: str = "trade_date") -> pd.DataFrame:
    optional = _normalize_merge_frame(frame if frame is not None else pd.DataFrame(), date_col=date_col)
    if optional.empty:
        return panel
    return panel.join(optional, how="left", rsuffix="_optional")


def _prepare_benchmark(benchmark_daily: pd.DataFrame, benchmark: str) -> pd.DataFrame:
    if benchmark_daily.empty:
        raise ValueError(f"TuShare index_daily data is empty for benchmark {benchmark}.")
    required = {"trade_date", "open", "close"}
    missing = required.difference(benchmark_daily.columns)
    if missing:
        raise KeyError(f"Missing benchmark columns: {sorted(missing)}")

    out = benchmark_daily.copy()
    out["date"] = _to_datetime_date(out["trade_date"])
    out = out.sort_values("date")
    close = out["close"].astype(float)
    out["benchmark_return"] = close.pct_change()
    out["benchmark_next_period_return"] = out["benchmark_return"].shift(-1)
    out["benchmark_cum_ret"] = (1.0 + out["benchmark_return"].fillna(0.0)).cumprod()
    out = out.rename(
        columns={
            "open": "benchmark_open",
            "close": "benchmark_close",
            "high": "benchmark_high",
            "low": "benchmark_low",
        }
    )
    keep = [
        col
        for col in (
            "date",
            "benchmark_open",
            "benchmark_close",
            "benchmark_high",
            "benchmark_low",
            "benchmark_return",
            "benchmark_next_period_return",
            "benchmark_cum_ret",
        )
        if col in out.columns
    ]
    return out[keep].drop_duplicates(subset=["date"]).set_index("date").sort_index()


def _merge_stock_basic(panel: pd.DataFrame, stock_basic: pd.DataFrame | None) -> pd.DataFrame:
    if stock_basic is None or stock_basic.empty or "ts_code" not in stock_basic.columns:
        if "is_st" not in panel.columns:
            panel["is_st"] = False
        return panel

    basic = stock_basic.copy()
    basic["ticker"] = basic["ts_code"].astype(str)
    basic = basic.drop(columns=["ts_code"]).drop_duplicates(subset=["ticker"], keep="last")
    out = panel.reset_index().merge(basic, on="ticker", how="left").set_index(["date", "ticker"]).sort_index()
    if "name" in out.columns:
        out["is_st"] = out["name"].astype(str).str.contains("ST", case=False, na=False)
    else:
        out["is_st"] = False
    if "list_date" in out.columns:
        list_date = _to_datetime_date(out["list_date"])
        date_values = pd.Series(out.index.get_level_values("date"), index=out.index)
        out["listed_days"] = (date_values - list_date).dt.days
    return out


def _apply_adjusted_prices(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    if "adj_factor" not in out.columns:
        return out
    for column in ("open", "high", "low", "close", "vwap"):
        if column in out.columns:
            out[f"{column}_adj"] = out[column].astype(float) * out["adj_factor"].astype(float)
    return out


def _add_returns(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    price_col = "close_adj" if "close_adj" in out.columns else "close"
    close = out[price_col].astype(float)
    out["return_1d"] = close.groupby(level="ticker", sort=False).pct_change()
    out["next_period_return"] = out["return_1d"].groupby(level="ticker", sort=False).shift(-1)
    return out


def _add_limit_flags(panel: pd.DataFrame, eps: float = 1e-6) -> pd.DataFrame:
    out = panel.copy()
    if "up_limit" in out.columns:
        out["hit_up_limit"] = out["close"].astype(float) >= (out["up_limit"].astype(float) - eps)
    else:
        out["hit_up_limit"] = False
    if "down_limit" in out.columns:
        out["hit_down_limit"] = out["close"].astype(float) <= (out["down_limit"].astype(float) + eps)
    else:
        out["hit_down_limit"] = False
    return out


def _add_suspend_flags(panel: pd.DataFrame, suspend: pd.DataFrame | None) -> pd.DataFrame:
    out = panel.copy()
    out["is_suspended"] = False
    if suspend is None or suspend.empty or "ts_code" not in suspend.columns:
        return out

    date_col = "trade_date"
    if date_col not in suspend.columns and "suspend_date" in suspend.columns:
        date_col = "suspend_date"
    suspended = _normalize_merge_frame(suspend, date_col=date_col)
    if suspended.empty:
        return out
    marker = pd.Series(True, index=suspended.index, name="_suspend_marker")
    out = out.join(marker, how="left")
    out["is_suspended"] = out["_suspend_marker"].fillna(False).astype(bool)
    return out.drop(columns=["_suspend_marker"])


def _complete_calendar(
    panel: pd.DataFrame,
    trade_dates: list[str] | None,
    tickers: tuple[str, ...],
) -> pd.DataFrame:
    if not trade_dates:
        return panel

    dates = pd.to_datetime(pd.Series(trade_dates), format="%Y%m%d", errors="coerce").dropna().unique()
    ticker_values = list(tickers) if tickers else sorted(panel.index.get_level_values("ticker").unique())
    full_index = pd.MultiIndex.from_product(
        [pd.Index(dates, name="date").sort_values(), ticker_values],
        names=["date", "ticker"],
    )
    out = panel.reindex(full_index)
    missing_price = out["close"].isna() if "close" in out.columns else pd.Series(True, index=out.index)
    out["is_suspended"] = missing_price.fillna(True).astype(bool)
    return out


def standardize_tushare_cn_daily_panel(
    *,
    daily: pd.DataFrame,
    benchmark_daily: pd.DataFrame,
    benchmark: str = "000300.SH",
    daily_basic: pd.DataFrame | None = None,
    adj_factor: pd.DataFrame | None = None,
    limits: pd.DataFrame | None = None,
    suspend: pd.DataFrame | None = None,
    stock_basic: pd.DataFrame | None = None,
    trade_dates: list[str] | None = None,
    tickers: tuple[str, ...] = (),
    factor_families: tuple[str, ...] = (),
    complete_calendar: bool = False,
    adjusted_features: bool = True,
) -> pd.DataFrame:
    """Normalize TuShare A-share daily data into the Money Tree date/ticker contract."""
    panel = _standardize_daily(daily)
    panel = _merge_optional(panel, daily_basic)
    panel = _merge_optional(panel, adj_factor)
    panel = _apply_adjusted_prices(panel)
    panel = _add_returns(panel)
    panel = _merge_optional(panel, limits)
    panel = _add_limit_flags(panel)
    panel = _add_suspend_flags(panel, suspend)
    panel = _merge_stock_basic(panel, stock_basic)

    if complete_calendar:
        panel = _complete_calendar(panel, trade_dates=trade_dates, tickers=tickers)

    benchmark_frame = _prepare_benchmark(benchmark_daily, benchmark=benchmark)
    panel = panel.join(benchmark_frame, on="date", how="left")

    if factor_families:
        panel = add_factor_family_features(
            panel,
            factor_families,
            adjusted=adjusted_features,
        )
    return ensure_date_ticker_index(panel).sort_index()


def _fetch_stock_basic(pro) -> pd.DataFrame:
    fields = "ts_code,symbol,name,area,industry,market,exchange,list_date,delist_date,list_status,is_hs"
    frames: list[pd.DataFrame] = []
    for status in ("L", "D", "P"):
        try:
            frames.append(
                _call_api(
                    pro,
                    "stock_basic",
                    exchange="",
                    list_status=status,
                    fields=fields,
                )
            )
        except Exception:
            continue
    return _concat(frames)


def fetch_tushare_cn_daily_panel(
    config: TushareDailyConfig,
    *,
    pro=None,
) -> pd.DataFrame:
    """Fetch and normalize a TuShare daily A-share panel."""
    client = pro if pro is not None else create_tushare_client(config.token, env_file=config.env_file)
    start_date = _normalize_date_str(config.start_date)
    end_date = _normalize_date_str(config.end_date)
    trade_dates = _fetch_trade_dates(client, start_date, end_date)

    tickers = tuple(str(ticker).strip() for ticker in config.tickers if str(ticker).strip())
    daily = _fetch_by_trade_date(client, "daily", trade_dates, tickers=tickers)
    benchmark_daily = _call_api(
        client,
        "index_daily",
        ts_code=config.benchmark,
        start_date=start_date,
        end_date=end_date,
    )
    daily_basic = (
        _fetch_by_trade_date(
            client,
            "daily_basic",
            trade_dates,
            tickers=tickers,
            fields=(
                "ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,"
                "ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv"
            ),
        )
        if config.include_daily_basic
        else None
    )
    adj_factor = (
        _fetch_by_trade_date(client, "adj_factor", trade_dates, tickers=tickers)
        if config.include_adj_factor
        else None
    )
    limits = (
        _fetch_by_trade_date(client, "stk_limit", trade_dates, tickers=tickers)
        if config.include_limits
        else None
    )
    suspend = (
        _fetch_by_trade_date(client, "suspend_d", trade_dates, tickers=tickers)
        if config.include_suspend
        else None
    )
    stock_basic = _fetch_stock_basic(client) if config.include_stock_basic else None

    return standardize_tushare_cn_daily_panel(
        daily=daily,
        benchmark_daily=benchmark_daily,
        benchmark=config.benchmark,
        daily_basic=daily_basic,
        adj_factor=adj_factor,
        limits=limits,
        suspend=suspend,
        stock_basic=stock_basic,
        trade_dates=trade_dates,
        tickers=tickers,
        factor_families=config.factor_families,
        complete_calendar=config.complete_calendar,
        adjusted_features=config.adjusted_features,
    )
