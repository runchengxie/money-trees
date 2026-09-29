"""Fast, pandas-compatible rolling rank primitives used by classic factors."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_rank_last_array(
    values: np.ndarray,
    window: int,
    *,
    min_periods: int | None = None,
) -> np.ndarray:
    """Return the percentile rank of the last value in each rolling window."""
    array = np.asarray(values, dtype=float)
    size = int(array.size)
    width = max(1, int(window))
    required = width if min_periods is None else max(1, int(min_periods))
    result = np.full(size, np.nan, dtype=float)
    if size == 0:
        return result

    prefix_end = min(size, width - 1)
    for position in range(prefix_end):
        start = max(0, position - width + 1)
        sample = array[start : position + 1]
        valid = ~np.isnan(sample)
        current = sample[position - start]
        if np.isnan(current) or int(valid.sum()) < required:
            continue
        usable = sample[valid]
        result[position] = (
            np.count_nonzero(usable < current)
            + (np.count_nonzero(usable == current) + 1.0) / 2.0
        ) / usable.size

    if size < width:
        return result

    windows = np.lib.stride_tricks.sliding_window_view(array, width)
    current = windows[:, -1]
    valid = ~np.isnan(windows)
    valid_count = valid.sum(axis=1)
    eligible = (~np.isnan(current)) & (valid_count >= required)
    if np.any(eligible):
        less = ((windows < current[:, None]) & valid).sum(axis=1)
        equal = ((windows == current[:, None]) & valid).sum(axis=1)
        numerator = less + (equal + 1.0) / 2.0
        ranked = np.full_like(numerator, np.nan, dtype=float)
        np.divide(numerator, valid_count, out=ranked, where=valid_count > 0)
        result[width - 1 :] = np.where(eligible, ranked, np.nan)
    return result


def rolling_rank_last(
    series: pd.Series,
    window: int,
    *,
    min_periods: int | None = None,
) -> pd.Series:
    """Apply :func:`rolling_rank_last_array` independently per ticker."""
    if not isinstance(series.index, pd.MultiIndex) or "ticker" not in series.index.names:
        raise ValueError("rolling rank requires a MultiIndex with a ticker level")
    values = series.to_numpy(dtype=float, copy=False)
    output = np.full(len(series), np.nan, dtype=float)
    for positions in series.groupby(level="ticker", sort=False).indices.values():
        positions = np.asarray(positions, dtype=np.intp)
        output[positions] = rolling_rank_last_array(
            values[positions], window, min_periods=min_periods
        )
    return pd.Series(output, index=series.index, name=series.name)


__all__ = ["rolling_rank_last", "rolling_rank_last_array"]
