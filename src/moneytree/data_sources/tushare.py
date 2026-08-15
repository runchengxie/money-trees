from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from moneytree.data import (
    DEFAULT_PARQUET_COMPRESSION,
    ensure_date_ticker_index,
    parquet_write_options,
)
from moneytree.data_quality import (
    DATA_QUALITY_MODES_WITH_OFF,
    build_tushare_panel_quality_result,
    enforce_data_quality_result,
    validate_data_quality_mode,
)
from moneytree.factors import add_factor_family_features
from moneytree.metadata import (
    dataframe_content_hash,
    dataframe_schema_hash,
    stable_json_dumps,
    stable_json_hash,
)

TOKEN_ENV_NAMES = ("TUSHARE_TOKEN", "TUSHARE_PRO_TOKEN", "TS_TOKEN", "TUSHARE_API_KEY")
TUSHARE_PROXY_MODES = ("direct", "env", "proxy")
TUSHARE_SANITY_CHECK_MODES = DATA_QUALITY_MODES_WITH_OFF
DEFAULT_TUSHARE_REQUEST_INTERVAL_SECONDS = 0.0
DEFAULT_TUSHARE_RATE_LIMIT_RETRIES = 3
DEFAULT_TUSHARE_RATE_LIMIT_WAIT_SECONDS = 65.0
_PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)
_NO_PROXY_ENV_NAMES = ("NO_PROXY", "no_proxy")
_TUSHARE_NO_PROXY_HOSTS = ("api.waditu.com", "waditu.com")
_PROXY_ENV_LOCK = threading.RLock()
_TUSHARE_RATE_LIMIT_LOCK = threading.RLock()
_LAST_TUSHARE_API_CALL_MONOTONIC: float | None = None


@dataclass(frozen=True)
class _TushareApiOptions:
    proxy_mode: str = "direct"
    proxy_url: str | None = None
    fallback_direct: bool = True
    request_interval_seconds: float = DEFAULT_TUSHARE_REQUEST_INTERVAL_SECONDS
    rate_limit_retries: int = DEFAULT_TUSHARE_RATE_LIMIT_RETRIES
    rate_limit_wait_seconds: float = DEFAULT_TUSHARE_RATE_LIMIT_WAIT_SECONDS


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
    cache_dir: str | Path | None = None
    refresh_cache: bool = False
    refresh_recent_days: int = 0
    show_progress: bool = False
    progress_every: int = 50
    factor_dtype: str = "float32"
    proxy_mode: str = "direct"
    proxy_url: str | None = None
    fallback_direct: bool = True
    request_interval_seconds: float = DEFAULT_TUSHARE_REQUEST_INTERVAL_SECONDS
    rate_limit_retries: int = DEFAULT_TUSHARE_RATE_LIMIT_RETRIES
    rate_limit_wait_seconds: float = DEFAULT_TUSHARE_RATE_LIMIT_WAIT_SECONDS
    sanity_check: str = "warn"
    cache_compression: str = DEFAULT_PARQUET_COMPRESSION
    cache_compression_level: int | None = None
    cache_row_group_size: int | None = None
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


def _emit_progress(message: str, *, enabled: bool) -> None:
    if enabled:
        print(message, file=sys.stderr, flush=True)


def _merge_no_proxy(*values: str | None) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in (value or "").split(","):
            item = part.strip()
            key = item.lower()
            if item and key not in seen:
                parts.append(item)
                seen.add(key)
    return ",".join(parts)


def _validate_proxy_settings(mode: str, proxy_url: str | None = None) -> None:
    if mode not in TUSHARE_PROXY_MODES:
        choices = ", ".join(TUSHARE_PROXY_MODES)
        raise ValueError(f"Unsupported TuShare proxy mode '{mode}'. Expected one of: {choices}.")
    if mode == "proxy" and not proxy_url:
        raise ValueError("TuShare proxy_url is required when proxy_mode is 'proxy'.")


def _validate_sanity_check_mode(mode: str) -> None:
    validate_data_quality_mode(mode, allow_off=True, label="TuShare sanity_check mode")


@contextmanager
def _temporary_proxy_mode(mode: str, proxy_url: str | None = None):
    _validate_proxy_settings(mode, proxy_url)

    names = (*_PROXY_ENV_NAMES, *_NO_PROXY_ENV_NAMES)
    with _PROXY_ENV_LOCK:
        original = {name: os.environ.get(name) for name in names}
        try:
            if mode == "direct":
                for name in _PROXY_ENV_NAMES:
                    os.environ.pop(name, None)
                no_proxy = _merge_no_proxy(
                    os.environ.get("NO_PROXY"),
                    os.environ.get("no_proxy"),
                    ",".join(_TUSHARE_NO_PROXY_HOSTS),
                )
                os.environ["NO_PROXY"] = no_proxy
                os.environ["no_proxy"] = no_proxy
            elif mode == "proxy":
                for name in _PROXY_ENV_NAMES:
                    os.environ[name] = str(proxy_url)
                for name in _NO_PROXY_ENV_NAMES:
                    os.environ.pop(name, None)
            yield
        finally:
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def _looks_like_proxy_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = type(current).__name__.lower()
        text = str(current).lower()
        if "proxy" in name or "proxy" in text:
            return True
        current = current.__cause__ or current.__context__
    return False


def _looks_like_rate_limit_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    needles = (
        "频率超限",
        "频次",
        "rate limit",
        "too many requests",
        "requests per minute",
        "500次/分钟",
    )
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).lower()
        if any(needle in text for needle in needles):
            return True
        current = current.__cause__ or current.__context__
    return False


def _wait_for_tushare_request_interval(interval_seconds: float) -> None:
    interval = max(0.0, float(interval_seconds))
    if interval <= 0:
        return

    global _LAST_TUSHARE_API_CALL_MONOTONIC
    with _TUSHARE_RATE_LIMIT_LOCK:
        now = time.monotonic()
        if _LAST_TUSHARE_API_CALL_MONOTONIC is not None:
            remaining = interval - (now - _LAST_TUSHARE_API_CALL_MONOTONIC)
            if remaining > 0:
                time.sleep(remaining)
                now = time.monotonic()
        _LAST_TUSHARE_API_CALL_MONOTONIC = now


def _invoke_tushare_method(
    method,
    clean_params: dict[str, Any],
    *,
    proxy_mode: str,
    proxy_url: str | None,
    request_interval_seconds: float,
):
    _wait_for_tushare_request_interval(request_interval_seconds)
    with _temporary_proxy_mode(proxy_mode, proxy_url):
        return method(**clean_params)


def _call_api(
    pro,
    api_name: str,
    *,
    api_options: _TushareApiOptions | None = None,
    **params,
) -> pd.DataFrame:
    options = api_options or _TushareApiOptions()
    method = getattr(pro, api_name)
    clean_params = {key: value for key, value in params.items() if value is not None}
    retries = max(0, int(options.rate_limit_retries))
    attempts = 0
    while True:
        try:
            try:
                out = _invoke_tushare_method(
                    method,
                    clean_params,
                    proxy_mode=options.proxy_mode,
                    proxy_url=options.proxy_url,
                    request_interval_seconds=options.request_interval_seconds,
                )
            except Exception as exc:
                if (
                    options.proxy_mode != "direct"
                    and options.fallback_direct
                    and _looks_like_proxy_error(exc)
                ):
                    warnings.warn(
                        (
                            f"TuShare API '{api_name}' failed through proxy mode "
                            f"'{options.proxy_mode}'; retrying direct."
                        ),
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    out = _invoke_tushare_method(
                        method,
                        clean_params,
                        proxy_mode="direct",
                        proxy_url=None,
                        request_interval_seconds=options.request_interval_seconds,
                    )
                else:
                    raise
            return out if isinstance(out, pd.DataFrame) else pd.DataFrame(out)
        except Exception as exc:
            if not _looks_like_rate_limit_error(exc) or attempts >= retries:
                raise
            attempts += 1
            wait_seconds = max(0.0, float(options.rate_limit_wait_seconds))
            warnings.warn(
                (
                    f"TuShare API '{api_name}' hit a rate limit; sleeping "
                    f"{wait_seconds:g}s before retry {attempts}/{retries}."
                ),
                RuntimeWarning,
                stacklevel=2,
            )
            if wait_seconds > 0:
                time.sleep(wait_seconds)


def _resolve_cache_dir(cache_dir: str | Path | None) -> Path | None:
    if cache_dir is None:
        return None
    path = Path(cache_dir)
    return path if str(path) else None


def _trade_date_cache_path(cache_dir: Path, api_name: str, trade_date: str) -> Path:
    return cache_dir / api_name / f"trade_date={trade_date}.parquet"


def _recent_trade_dates(trade_dates: list[str], refresh_recent_days: int) -> set[str]:
    if refresh_recent_days <= 0:
        return set()
    return set(trade_dates[-int(refresh_recent_days) :])


def _relative_cache_path(cache_dir: Path, cache_path: Path) -> str:
    try:
        return cache_path.relative_to(cache_dir).as_posix()
    except ValueError:
        return cache_path.as_posix()


def _ensure_raw_cache_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_cache (
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
    existing = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(raw_cache)").fetchall()
    }
    columns = {
        "request_hash": "TEXT NOT NULL DEFAULT ''",
        "params_json": "TEXT NOT NULL DEFAULT '{}'",
        "schema_hash": "TEXT NOT NULL DEFAULT ''",
        "content_hash": "TEXT NOT NULL DEFAULT ''",
        "updated_at_utc": "TEXT NOT NULL DEFAULT ''",
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE raw_cache ADD COLUMN {name} {definition}")


def _write_cache_manifest(
    *,
    cache_dir: Path,
    api_name: str,
    trade_date: str,
    cache_path: Path,
    frame: pd.DataFrame,
    request_params: dict[str, Any],
) -> None:
    manifest_path = cache_dir / "manifest.sqlite"
    columns_json = json.dumps(
        [str(column) for column in frame.columns],
        ensure_ascii=False,
    )
    params_payload = {
        "api_name": api_name,
        "params": request_params,
        "source": "tushare",
    }
    params_json = stable_json_dumps(params_payload)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(manifest_path) as conn:
        _ensure_raw_cache_table(conn)
        conn.execute(
            """
            INSERT INTO raw_cache (
                source, api_name, trade_date, path, rows, columns_json,
                request_hash, params_json, schema_hash, content_hash,
                created_at_utc, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, api_name, trade_date) DO UPDATE SET
                path = excluded.path,
                rows = excluded.rows,
                columns_json = excluded.columns_json,
                request_hash = excluded.request_hash,
                params_json = excluded.params_json,
                schema_hash = excluded.schema_hash,
                content_hash = excluded.content_hash,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                "tushare",
                api_name,
                trade_date,
                _relative_cache_path(cache_dir, cache_path),
                int(len(frame)),
                columns_json,
                stable_json_hash(params_payload),
                params_json,
                dataframe_schema_hash(frame),
                dataframe_content_hash(frame),
                now,
                now,
            ),
        )


def _fetch_trade_dates(
    pro,
    start_date: str,
    end_date: str,
    *,
    api_options: _TushareApiOptions | None = None,
) -> list[str]:
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
            api_options=api_options,
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
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
    refresh_recent_days: int = 0,
    show_progress: bool = False,
    progress_every: int = 50,
    cache_compression: str = DEFAULT_PARQUET_COMPRESSION,
    cache_compression_level: int | None = None,
    cache_row_group_size: int | None = None,
    api_options: _TushareApiOptions | None = None,
    **extra_params,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    resolved_cache_dir = _resolve_cache_dir(cache_dir)
    recent_dates = _recent_trade_dates(trade_dates, refresh_recent_days)
    total = len(trade_dates)
    interval = max(1, int(progress_every))
    rows = 0
    cache_hits = 0
    fetched = 0

    for idx, trade_date in enumerate(trade_dates, start=1):
        cache_path = (
            _trade_date_cache_path(resolved_cache_dir, api_name, trade_date)
            if resolved_cache_dir is not None
            else None
        )
        should_refresh = refresh_cache or trade_date in recent_dates
        if cache_path is not None and cache_path.exists() and not should_refresh:
            frame = pd.read_parquet(cache_path)
            cache_hits += 1
        else:
            request_params = {
                "trade_date": trade_date,
                "fields": fields,
                **extra_params,
            }
            request_params = {
                key: value for key, value in request_params.items() if value is not None
            }
            frame = _call_api(
                pro,
                api_name,
                trade_date=trade_date,
                fields=fields,
                api_options=api_options,
                **extra_params,
            )
            fetched += 1
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                frame.to_parquet(
                    cache_path,
                    index=False,
                    **parquet_write_options(
                        compression=cache_compression,
                        compression_level=cache_compression_level,
                        row_group_size=cache_row_group_size,
                    ),
                )
                _write_cache_manifest(
                    cache_dir=resolved_cache_dir,
                    api_name=api_name,
                    trade_date=trade_date,
                    cache_path=cache_path,
                    frame=frame,
                    request_params=request_params,
                )
        filtered = _filter_tickers(frame, tickers)
        frames.append(filtered)
        rows += len(filtered)
        if show_progress and (idx == 1 or idx % interval == 0 or idx == total):
            _emit_progress(
                (
                    f"[tushare:{api_name}] {idx}/{total} trade_dates "
                    f"rows={rows} cache_hits={cache_hits} fetched={fetched}"
                ),
                enabled=show_progress,
            )
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
        panel.attrs["is_st_source"] = "default_false_no_stock_basic"
        panel.attrs["is_st_point_in_time"] = False
        return panel

    basic = stock_basic.copy()
    basic["ticker"] = basic["ts_code"].astype(str)
    basic = basic.drop(columns=["ts_code"]).drop_duplicates(subset=["ticker"], keep="last")
    out = panel.reset_index().merge(basic, on="ticker", how="left").set_index(["date", "ticker"]).sort_index()
    if "name" in out.columns:
        out["is_st"] = out["name"].astype(str).str.contains("ST", case=False, na=False)
        out.attrs["is_st_source"] = "tushare_stock_basic_latest_name_flag"
        out.attrs["is_st_point_in_time"] = False
    else:
        out["is_st"] = False
        out.attrs["is_st_source"] = "default_false_no_stock_basic_name"
        out.attrs["is_st_point_in_time"] = False
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
    suspended = suspended.loc[~suspended.index.duplicated(keep="last")]
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


def _emit_tushare_sanity_report(
    panel: pd.DataFrame,
    *,
    stage: str,
    mode: str,
    show_progress: bool,
    trade_dates: list[str] | None = None,
    expected_start: str | None = None,
    expected_end: str | None = None,
    factor_families: tuple[str, ...] = (),
) -> None:
    if mode == "off":
        return
    _validate_sanity_check_mode(mode)
    result = build_tushare_panel_quality_result(
        panel,
        expected_start=expected_start,
        expected_end=expected_end,
        trade_dates=trade_dates,
        factor_families=factor_families,
    )
    for line in result.to_lines(prefix=f"[tushare:sanity:{stage}]"):
        _emit_progress(line, enabled=show_progress)
    enforce_data_quality_result(
        result,
        mode=mode,
        error_message=f"TuShare data sanity check failed at stage '{stage}'",
        warning_message=f"TuShare data sanity check reported issues at stage '{stage}'",
    )


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
    factor_dtype: str = "float32",
    show_progress: bool = False,
    sanity_check: str = "off",
) -> pd.DataFrame:
    """Normalize TuShare A-share daily data into the Money Trees date/ticker contract."""
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

    _emit_tushare_sanity_report(
        panel,
        stage="base",
        mode=sanity_check,
        show_progress=show_progress,
        trade_dates=trade_dates,
        expected_start=trade_dates[0] if trade_dates else None,
        expected_end=trade_dates[-1] if trade_dates else None,
    )

    if factor_families:
        _emit_progress(
            (
                "[tushare:factors] generating "
                f"families={','.join(factor_families)} rows={len(panel)}"
            ),
            enabled=show_progress,
        )
        panel = add_factor_family_features(
            panel,
            factor_families,
            adjusted=adjusted_features,
            dtype=factor_dtype,
        )
        _emit_progress(
            (
                "[tushare:factors] generated "
                f"families={','.join(factor_families)} cols={len(panel.columns)}"
            ),
            enabled=show_progress,
        )

        _emit_tushare_sanity_report(
            panel,
            stage="final",
            mode=sanity_check,
            show_progress=show_progress,
            trade_dates=trade_dates,
            expected_start=trade_dates[0] if trade_dates else None,
            expected_end=trade_dates[-1] if trade_dates else None,
            factor_families=factor_families,
        )
    panel = ensure_date_ticker_index(panel).sort_index()
    if "is_st" in panel.columns:
        panel.attrs.setdefault("is_st_source", "tushare_stock_basic_latest_name_flag")
        panel.attrs.setdefault("is_st_point_in_time", False)
    return panel


def _fetch_stock_basic(
    pro,
    *,
    api_options: _TushareApiOptions | None = None,
) -> pd.DataFrame:
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
                    api_options=api_options,
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
    api_options = _TushareApiOptions(
        proxy_mode=config.proxy_mode,
        proxy_url=config.proxy_url,
        fallback_direct=config.fallback_direct,
        request_interval_seconds=config.request_interval_seconds,
        rate_limit_retries=config.rate_limit_retries,
        rate_limit_wait_seconds=config.rate_limit_wait_seconds,
    )
    _validate_proxy_settings(api_options.proxy_mode, api_options.proxy_url)
    _validate_sanity_check_mode(config.sanity_check)
    trade_dates = _fetch_trade_dates(client, start_date, end_date, api_options=api_options)
    _emit_progress(
        (
            f"[tushare] trade_dates={len(trade_dates)} "
            f"start={start_date} end={end_date}"
        ),
        enabled=config.show_progress,
    )

    tickers = tuple(str(ticker).strip() for ticker in config.tickers if str(ticker).strip())
    cache_kwargs = {
        "cache_dir": config.cache_dir,
        "refresh_cache": bool(config.refresh_cache),
        "refresh_recent_days": int(config.refresh_recent_days),
        "show_progress": bool(config.show_progress),
        "progress_every": int(config.progress_every),
        "cache_compression": config.cache_compression,
        "cache_compression_level": config.cache_compression_level,
        "cache_row_group_size": config.cache_row_group_size,
        "api_options": api_options,
    }
    daily = _fetch_by_trade_date(
        client,
        "daily",
        trade_dates,
        tickers=tickers,
        **cache_kwargs,
    )
    _emit_progress(
        f"[tushare:index_daily] fetching benchmark={config.benchmark}",
        enabled=config.show_progress,
    )
    benchmark_daily = _call_api(
        client,
        "index_daily",
        ts_code=config.benchmark,
        start_date=start_date,
        end_date=end_date,
        api_options=api_options,
    )
    daily_basic = (
        _fetch_by_trade_date(
            client,
            "daily_basic",
            trade_dates,
            tickers=tickers,
            **cache_kwargs,
            fields=(
                "ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,"
                "ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv"
            ),
        )
        if config.include_daily_basic
        else None
    )
    adj_factor = (
        _fetch_by_trade_date(
            client,
            "adj_factor",
            trade_dates,
            tickers=tickers,
            **cache_kwargs,
        )
        if config.include_adj_factor
        else None
    )
    limits = (
        _fetch_by_trade_date(
            client,
            "stk_limit",
            trade_dates,
            tickers=tickers,
            **cache_kwargs,
        )
        if config.include_limits
        else None
    )
    suspend = (
        _fetch_by_trade_date(
            client,
            "suspend_d",
            trade_dates,
            tickers=tickers,
            **cache_kwargs,
        )
        if config.include_suspend
        else None
    )
    if config.include_stock_basic:
        _emit_progress(
            "[tushare:stock_basic] fetching list_status=L,D,P",
            enabled=config.show_progress,
        )
        stock_basic = _fetch_stock_basic(client, api_options=api_options)
    else:
        stock_basic = None
    _emit_progress(
        "[tushare:standardize] building canonical date,ticker panel",
        enabled=config.show_progress,
    )

    panel = standardize_tushare_cn_daily_panel(
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
        factor_dtype=config.factor_dtype,
        show_progress=config.show_progress,
        sanity_check=config.sanity_check,
    )
    _emit_progress(
        f"[tushare:done] rows={len(panel)} cols={len(panel.columns)}",
        enabled=config.show_progress,
    )
    return panel
