from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from moneytree.data import (
    NON_FEATURE_COLUMNS,
    apply_feature_lag,
    ensure_date_ticker_index,
    fill_missing_with_reference,
    get_feature_columns,
    load_market_data,
    make_labels,
    preprocess_data,
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


def test_fill_missing_with_reference_uses_reference_statistics_only() -> None:
    reference = pd.DataFrame(
        {
            "f_num": [1.0, 2.0, np.nan, 4.0],
            "f_text": ["x", None, "y", "z"],
        }
    )
    frame = pd.DataFrame(
        {
            "f_num": [np.nan, 1000.0, 2000.0],
            "f_text": [None, "keep", None],
        }
    )

    filled = fill_missing_with_reference(frame=frame, reference=reference)
    assert filled.loc[0, "f_num"] == 2.0
    assert filled.loc[0, "f_text"] == "missing"
    assert filled.loc[1, "f_text"] == "keep"


def test_preprocess_data_pred_rel_return_missing_column_raises_key_error() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2021-03-31", "2021-03-31"],
            "ticker": ["A", "B"],
            "next_period_return": [0.01, -0.02],
            "spy_next_period_return": [0.005, 0.005],
            "spy_cum_ret": [100.0, 100.0],
        }
    )

    with pytest.raises(KeyError, match="pred_rel_return"):
        preprocess_data(raw, label_source="pred_rel_return", apply_global_fill=False)


def test_load_market_data_unsupported_suffix_raises_value_error(tmp_path) -> None:
    bad_path = tmp_path / "sample.csv"
    bad_path.write_text("date,ticker\n2021-01-01,A\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported data format"):
        load_market_data(bad_path)


def test_apply_feature_lag_shifts_by_ticker_and_drops_all_missing_rows() -> None:
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2021-01-31"), "A"),
            (pd.Timestamp("2021-02-28"), "A"),
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-01-31"), "B"),
            (pd.Timestamp("2021-02-28"), "B"),
            (pd.Timestamp("2021-03-31"), "B"),
        ],
        names=["date", "ticker"],
    )
    frame = pd.DataFrame(
        {
            "f1": [1.0, 2.0, 3.0, 10.0, 20.0, 30.0],
            "f2": [4.0, 5.0, 6.0, 40.0, 50.0, 60.0],
            "next_period_return": [0.01, 0.02, 0.03, -0.01, -0.02, -0.03],
        },
        index=idx,
    )

    lagged = apply_feature_lag(frame, feature_columns=["f1", "f2"], lag_periods=1)

    assert len(lagged) == 4
    assert np.isclose(float(lagged.loc[(pd.Timestamp("2021-02-28"), "A"), "f1"]), 1.0)
    assert np.isclose(float(lagged.loc[(pd.Timestamp("2021-03-31"), "A"), "f1"]), 2.0)
    assert np.isclose(float(lagged.loc[(pd.Timestamp("2021-02-28"), "B"), "f2"]), 40.0)
