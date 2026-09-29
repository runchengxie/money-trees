from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from moneytree.data import ensure_date_ticker_index, normalize_factor_dtype
from moneytree.factors.rolling import rolling_rank_last

PRICE_FIELDS = ("open", "high", "low", "close", "vwap")
ALPHA360_FIELDS = ("open", "high", "low", "close", "vwap", "volume")


def _resolve_column(frame: pd.DataFrame, base_name: str, adjusted: bool) -> str:
    if adjusted:
        adjusted_name = f"{base_name}_adj"
        if adjusted_name in frame.columns:
            return adjusted_name
    if base_name in frame.columns:
        return base_name
    raise KeyError(f"Missing required Alpha feature input column: {base_name}")


def _series(frame: pd.DataFrame, base_name: str, adjusted: bool = True) -> pd.Series:
    return frame[_resolve_column(frame, base_name, adjusted)].astype(float)


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = denominator.replace(0, np.nan)
    return numerator / denom


def _normalize_feature_dtype(dtype: str | None) -> str | None:
    return normalize_factor_dtype(dtype) if dtype is not None else None


def _add_feature(
    values: dict[str, pd.Series],
    name: str,
    series: pd.Series,
    dtype: str | None,
) -> None:
    values[name] = series.astype(dtype) if dtype is not None else series


def _by_ticker(series: pd.Series):
    return series.groupby(level="ticker", sort=False)


def _shift(series: pd.Series, periods: int) -> pd.Series:
    return _by_ticker(series).shift(int(periods))


def _pct_change(series: pd.Series, periods: int = 1) -> pd.Series:
    return _by_ticker(series).pct_change(int(periods))


def _rolling_mean(series: pd.Series, window: int) -> pd.Series:
    return _by_ticker(series).transform(lambda s: s.rolling(window, min_periods=1).mean())


def _rolling_std(series: pd.Series, window: int) -> pd.Series:
    return _by_ticker(series).transform(lambda s: s.rolling(window, min_periods=2).std())


def _rolling_max(series: pd.Series, window: int) -> pd.Series:
    return _by_ticker(series).transform(lambda s: s.rolling(window, min_periods=1).max())


def _rolling_min(series: pd.Series, window: int) -> pd.Series:
    return _by_ticker(series).transform(lambda s: s.rolling(window, min_periods=1).min())


def _rolling_quantile(series: pd.Series, window: int, q: float) -> pd.Series:
    return _by_ticker(series).transform(
        lambda s: s.rolling(window, min_periods=1).quantile(float(q))
    )


def _rolling_rank_latest(series: pd.Series, window: int) -> pd.Series:
    return rolling_rank_last(series, window, min_periods=1)


def _rolling_sum(series: pd.Series, window: int) -> pd.Series:
    return _by_ticker(series).transform(lambda s: s.rolling(window, min_periods=1).sum())


def build_alpha360_features(
    frame: pd.DataFrame,
    *,
    lookback: int = 60,
    adjusted: bool = True,
    prefix: str = "alpha360",
    dtype: str | None = None,
) -> pd.DataFrame:
    """
    Build a Qlib-style Alpha360 daily sequence baseline.

    The output contains 6 fields x 60 lags by default. Price-like fields are normalized
    to current close, while volume is normalized to current volume.
    """
    panel = ensure_date_ticker_index(frame)
    normalized_dtype = _normalize_feature_dtype(dtype)
    close = _series(panel, "close", adjusted=adjusted)
    volume = _series(panel, "volume", adjusted=False)
    feature_values: dict[str, pd.Series] = {}

    for field in ALPHA360_FIELDS:
        base = volume if field == "volume" else _series(panel, field, adjusted=adjusted)
        denom = volume if field == "volume" else close
        for lag in range(int(lookback)):
            shifted = _shift(base, lag)
            _add_feature(
                feature_values,
                f"{prefix}_{field}_lag{lag:02d}",
                _safe_divide(shifted, denom) - 1.0,
                normalized_dtype,
            )

    return pd.DataFrame(feature_values, index=panel.index)


def build_alpha158_features(
    frame: pd.DataFrame,
    *,
    adjusted: bool = True,
    windows: Iterable[int] = (5, 10, 20, 30, 60),
    price_lags: int = 20,
    prefix: str = "alpha158",
    dtype: str | None = None,
) -> pd.DataFrame:
    """
    Build a compact Qlib-style Alpha158 daily feature baseline.

    This is intentionally a local baseline with the same daily OHLCV spirit and 158-column
    footprint. For byte-for-byte Qlib reproduction, generate Alpha158 in Qlib and merge
    the resulting columns into the Money Trees panel.
    """
    panel = ensure_date_ticker_index(frame)
    normalized_dtype = _normalize_feature_dtype(dtype)
    open_ = _series(panel, "open", adjusted=adjusted)
    high = _series(panel, "high", adjusted=adjusted)
    low = _series(panel, "low", adjusted=adjusted)
    close = _series(panel, "close", adjusted=adjusted)
    vwap = _series(panel, "vwap", adjusted=adjusted)
    volume = _series(panel, "volume", adjusted=False)
    amount = panel["amount"].astype(float) if "amount" in panel.columns else close * volume

    eps_range = (high - low).replace(0, np.nan)
    feature_values: dict[str, pd.Series] = {}
    open_close = pd.concat([open_, close], axis=1)
    high_minus_body = high - open_close.max(axis=1)
    body_minus_low = open_close.min(axis=1) - low

    _add_feature(feature_values, f"{prefix}_kmid", _safe_divide(close - open_, open_), normalized_dtype)
    _add_feature(feature_values, f"{prefix}_klen", _safe_divide(high - low, open_), normalized_dtype)
    _add_feature(feature_values, f"{prefix}_kmid2", _safe_divide(close - open_, eps_range), normalized_dtype)
    _add_feature(feature_values, f"{prefix}_kup", _safe_divide(high_minus_body, open_), normalized_dtype)
    _add_feature(
        feature_values,
        f"{prefix}_kup2",
        _safe_divide(high_minus_body, eps_range),
        normalized_dtype,
    )
    _add_feature(feature_values, f"{prefix}_klow", _safe_divide(body_minus_low, open_), normalized_dtype)
    _add_feature(
        feature_values,
        f"{prefix}_klow2",
        _safe_divide(body_minus_low, eps_range),
        normalized_dtype,
    )
    _add_feature(
        feature_values,
        f"{prefix}_ksft",
        _safe_divide(2.0 * close - high - low, open_),
        normalized_dtype,
    )
    _add_feature(
        feature_values,
        f"{prefix}_ksft2",
        _safe_divide(2.0 * close - high - low, eps_range),
        normalized_dtype,
    )

    for field, series in {
        "open": open_,
        "high": high,
        "low": low,
        "vwap": vwap,
    }.items():
        for lag in range(int(price_lags)):
            _add_feature(
                feature_values,
                f"{prefix}_{field}_lag{lag:02d}_rel_close",
                _safe_divide(_shift(series, lag), close) - 1.0,
                normalized_dtype,
            )

    daily_ret = _pct_change(close, 1)
    volume_ret = _pct_change(volume.replace(0, np.nan), 1)
    for window in [int(w) for w in windows]:
        rolling_high = _rolling_max(high, window)
        rolling_low = _rolling_min(low, window)
        range_window = (rolling_high - rolling_low).replace(0, np.nan)

        _add_feature(
            feature_values,
            f"{prefix}_roc_{window}",
            _safe_divide(close, _shift(close, window)) - 1.0,
            normalized_dtype,
        )
        _add_feature(
            feature_values,
            f"{prefix}_ma_{window}",
            _safe_divide(_rolling_mean(close, window), close) - 1.0,
            normalized_dtype,
        )
        _add_feature(
            feature_values,
            f"{prefix}_std_{window}",
            _rolling_std(daily_ret, window),
            normalized_dtype,
        )
        _add_feature(
            feature_values,
            f"{prefix}_max_{window}",
            _safe_divide(rolling_high, close) - 1.0,
            normalized_dtype,
        )
        _add_feature(
            feature_values,
            f"{prefix}_min_{window}",
            _safe_divide(rolling_low, close) - 1.0,
            normalized_dtype,
        )
        _add_feature(
            feature_values,
            f"{prefix}_q80_{window}",
            _safe_divide(_rolling_quantile(close, window, 0.8), close) - 1.0,
            normalized_dtype,
        )
        _add_feature(
            feature_values,
            f"{prefix}_q20_{window}",
            _safe_divide(_rolling_quantile(close, window, 0.2), close) - 1.0,
            normalized_dtype,
        )
        _add_feature(
            feature_values,
            f"{prefix}_rank_{window}",
            _rolling_rank_latest(close, window),
            normalized_dtype,
        )
        _add_feature(
            feature_values,
            f"{prefix}_rsv_{window}",
            _safe_divide(close - rolling_low, range_window),
            normalized_dtype,
        )
        _add_feature(
            feature_values,
            f"{prefix}_ret_mean_{window}",
            _rolling_mean(daily_ret, window),
            normalized_dtype,
        )

        _add_feature(
            feature_values,
            f"{prefix}_vma_{window}",
            _safe_divide(volume, _rolling_mean(volume, window)) - 1.0,
            normalized_dtype,
        )
        _add_feature(
            feature_values,
            f"{prefix}_vstd_{window}",
            _rolling_std(volume_ret, window),
            normalized_dtype,
        )
        _add_feature(
            feature_values,
            f"{prefix}_amount_ma_{window}",
            _safe_divide(amount, _rolling_mean(amount, window)) - 1.0,
            normalized_dtype,
        )

    _add_feature(
        feature_values,
        f"{prefix}_vwap_rel_close",
        _safe_divide(vwap, close) - 1.0,
        normalized_dtype,
    )
    _add_feature(
        feature_values,
        f"{prefix}_high_low_spread",
        _safe_divide(high - low, close),
        normalized_dtype,
    )
    _add_feature(
        feature_values,
        f"{prefix}_close_to_high",
        _safe_divide(close, high) - 1.0,
        normalized_dtype,
    )
    _add_feature(
        feature_values,
        f"{prefix}_close_to_low",
        _safe_divide(close, low) - 1.0,
        normalized_dtype,
    )

    features = pd.DataFrame(feature_values, index=panel.index)
    expected_count = 158
    if len(features.columns) != expected_count:
        raise RuntimeError(
            f"Alpha158 baseline generated {len(features.columns)} columns; expected {expected_count}."
        )
    return features


def add_factor_family_features(
    frame: pd.DataFrame,
    families: Iterable[str],
    *,
    adjusted: bool = True,
    dtype: str | None = None,
) -> pd.DataFrame:
    """Append supported local daily factor-family features to a panel."""
    panel = ensure_date_ticker_index(frame)
    normalized_dtype = _normalize_feature_dtype(dtype)
    out = panel.copy()
    for family in families:
        key = family.strip().lower().replace("-", "_")
        if key == "alpha158":
            features = build_alpha158_features(out, adjusted=adjusted, dtype=normalized_dtype)
        elif key == "alpha360":
            features = build_alpha360_features(out, adjusted=adjusted, dtype=normalized_dtype)
        else:
            raise ValueError(
                f"Unsupported local factor family '{family}'. "
                "Use 'alpha158' or 'alpha360', or merge external Alpha101/Alpha191 columns first."
            )
        out = out.join(features, how="left")
    return out
