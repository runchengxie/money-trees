from __future__ import annotations

import pandas as pd

from strategy.data import (
    NON_FEATURE_COLUMNS,
    ensure_date_ticker_index,
    get_feature_columns,
    make_labels,
)


def test_make_labels_threshold_mapping() -> None:
    rel = pd.Series([-0.10, -0.05, 0.00, 0.06], index=[0, 1, 2, 3])
    labels = make_labels(rel, threshold=0.05)
    assert labels.tolist() == [-1, 0, 0, 1]


def test_ensure_date_ticker_index_from_columns() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2021-01-02", "2021-01-01"],
            "ticker": ["B", "A"],
            "x": [1.0, 2.0],
        }
    )
    out = ensure_date_ticker_index(frame)
    assert isinstance(out.index, pd.MultiIndex)
    assert out.index.names == ["date", "ticker"]
    assert list(out.index.get_level_values("date")) == ["2021-01-01", "2021-01-02"]


def test_ensure_date_ticker_index_reorders_multiindex_levels() -> None:
    idx = pd.MultiIndex.from_tuples(
        [("A", "2021-01-02"), ("B", "2021-01-01")],
        names=["ticker", "date"],
    )
    frame = pd.DataFrame({"x": [1.0, 2.0]}, index=idx)
    out = ensure_date_ticker_index(frame)
    assert out.index.names == ["date", "ticker"]
    assert list(out.index.get_level_values("date")) == ["2021-01-01", "2021-01-02"]


def test_get_feature_columns_excludes_non_feature_columns() -> None:
    frame = pd.DataFrame(
        {
            "feature_num": [1.0, 2.0],
            "feature_bool": [True, False],
            "feature_text": ["x", "y"],
            "next_period_return": [0.01, 0.02],
            "rel_performance": [1, -1],
        }
    )
    features = get_feature_columns(frame)
    assert "feature_num" in features
    assert "feature_bool" in features
    assert "feature_text" not in features
    for col in NON_FEATURE_COLUMNS:
        assert col not in features
