from __future__ import annotations

import numpy as np
import pandas as pd

from moneytree.data import ensure_date_ticker_index


def to_wide(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Convert a long date/ticker panel column into a date x ticker matrix."""
    panel = ensure_date_ticker_index(frame)
    if column not in panel.columns:
        raise KeyError(f"Missing factor input column: {column}")
    return (
        panel[column]
        .reset_index()
        .pivot(index="date", columns="ticker", values=column)
        .sort_index()
    )


def from_wide(matrix: pd.DataFrame, name: str) -> pd.Series:
    """Convert a date x ticker matrix back to a ('date', 'ticker') Series."""
    out = matrix.stack(dropna=False).rename(name)
    out.index = out.index.set_names(["date", "ticker"])
    return out


def safe_divide(numerator: pd.DataFrame | pd.Series, denominator: pd.DataFrame | pd.Series):
    denom = denominator.replace(0, np.nan)
    return numerator / denom


def cs_rank(matrix: pd.DataFrame, pct: bool = True) -> pd.DataFrame:
    """Cross-sectional rank by date."""
    return matrix.rank(axis=1, pct=pct)


def delay(matrix: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    """Ticker-wise delay on a wide panel."""
    return matrix.shift(int(periods))


def delta(matrix: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    """Ticker-wise difference on a wide panel."""
    return matrix.diff(int(periods))


def rolling_corr(
    left: pd.DataFrame,
    right: pd.DataFrame,
    window: int,
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Ticker-wise rolling correlation."""
    return left.rolling(window, min_periods=min_periods or window).corr(right)


def rolling_cov(
    left: pd.DataFrame,
    right: pd.DataFrame,
    window: int,
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Ticker-wise rolling covariance."""
    return left.rolling(window, min_periods=min_periods or window).cov(right)


def ts_rank(matrix: pd.DataFrame, window: int, min_periods: int | None = None) -> pd.DataFrame:
    """Rank the latest value within each ticker's rolling window."""

    def _rank_last(values: np.ndarray) -> float:
        series = pd.Series(values)
        return float(series.rank(pct=True).iloc[-1])

    return matrix.rolling(window, min_periods=min_periods or window).apply(
        _rank_last,
        raw=True,
    )


def decay_linear(
    matrix: pd.DataFrame,
    window: int,
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Linearly weighted rolling mean with the newest observation receiving largest weight."""
    weights = np.arange(1, int(window) + 1, dtype=float)

    def _weighted(values: np.ndarray) -> float:
        valid = np.isfinite(values)
        if not valid.any():
            return float("nan")
        active_values = values[valid]
        active_weights = weights[-len(values) :][valid]
        denom = active_weights.sum()
        if denom <= 0:
            return float("nan")
        return float(np.dot(active_values, active_weights) / denom)

    return matrix.rolling(window, min_periods=min_periods or window).apply(
        _weighted,
        raw=True,
    )


def scale(matrix: pd.DataFrame, k: float = 1.0) -> pd.DataFrame:
    """Scale each date's absolute exposure to k."""
    denom = matrix.abs().sum(axis=1).replace(0, np.nan)
    return matrix.div(denom, axis=0) * float(k)


def signed_power(matrix: pd.DataFrame, power: float) -> pd.DataFrame:
    """Apply sign(x) * abs(x) ** power."""
    return np.sign(matrix) * np.power(matrix.abs(), float(power))


def adv(volume: pd.DataFrame, window: int, min_periods: int | None = None) -> pd.DataFrame:
    """Average daily volume on a wide volume matrix."""
    return volume.rolling(window, min_periods=min_periods or window).mean()
