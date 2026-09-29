import numpy as np
import pandas as pd

from moneytree.factors.rolling import rolling_rank_last, rolling_rank_last_array


def test_rolling_rank_array_matches_pandas_average_ties_and_nans() -> None:
    values = np.array([1.0, 3.0, 3.0, np.nan, 2.0, 4.0])
    expected = pd.Series(values).rolling(3).apply(
        lambda sample: sample.rank(pct=True).iloc[-1], raw=False
    ).to_numpy()
    actual = rolling_rank_last_array(values, 3, min_periods=3)
    np.testing.assert_allclose(actual, expected, equal_nan=True)


def test_rolling_rank_is_independent_per_ticker() -> None:
    index = pd.MultiIndex.from_product(
        [pd.date_range("2025-01-01", periods=3), ["A", "B"]],
        names=["date", "ticker"],
    )
    values = pd.Series([1.0, 3.0, 2.0, 2.0, 1.0, 3.0], index=index)
    actual = rolling_rank_last(values, 2, min_periods=1)
    expected = values.groupby(level="ticker", sort=False).transform(
        lambda group: group.rolling(2, min_periods=1).apply(
            lambda sample: sample.rank(pct=True).iloc[-1], raw=False
        )
    )
    pd.testing.assert_series_equal(actual, expected)
