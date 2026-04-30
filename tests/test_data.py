from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from moneytree.data import (
    DEFAULT_PARQUET_COMPRESSION,
    FACTOR_PREFIXES,
    NON_FEATURE_COLUMNS,
    apply_feature_lag,
    apply_missing_feature_policy,
    coerce_factor_columns,
    ensure_date_ticker_index,
    factor_columns,
    fill_missing_with_reference,
    filter_factor_columns,
    get_feature_columns,
    load_market_data,
    make_labels,
    normalize_factor_dtype,
    normalize_factor_prefixes,
    parquet_write_options,
    preprocess_data,
    save_market_data,
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


def test_factor_column_helpers_identify_and_normalize_alpha_columns() -> None:
    columns = ["alpha101_001", "alpha158_kmid", "feature", "alpha360_close_lag00"]

    assert FACTOR_PREFIXES == ("alpha101_", "alpha191_", "alpha158_", "alpha360_")
    assert factor_columns(columns) == ["alpha101_001", "alpha158_kmid", "alpha360_close_lag00"]
    assert normalize_factor_prefixes(["alpha158"], families=["alpha101"]) == (
        "alpha101_",
        "alpha158_",
    )


def test_coerce_factor_columns_only_changes_alpha_dtypes() -> None:
    frame = pd.DataFrame(
        {
            "alpha158_kmid": pd.Series([1.0, 2.0], dtype="float64"),
            "alpha360_close_lag00": pd.Series([0.1, 0.2], dtype="float64"),
            "feature_num": pd.Series([3.0, 4.0], dtype="float64"),
            "flag": [True, False],
        }
    )

    out = coerce_factor_columns(frame, "float32")

    assert str(out["alpha158_kmid"].dtype) == "float32"
    assert str(out["alpha360_close_lag00"].dtype) == "float32"
    assert str(out["feature_num"].dtype) == "float64"
    assert str(out["flag"].dtype) == "bool"


def test_coerce_factor_columns_sanitizes_nonfinite_and_float32_overflow() -> None:
    too_large_for_float32 = float(np.finfo(np.float32).max) * 2.0
    frame = pd.DataFrame(
        {
            "alpha101_001": [1.0, np.inf, -np.inf, too_large_for_float32],
            "feature_num": [1.0, np.inf, -np.inf, too_large_for_float32],
        }
    )

    out = coerce_factor_columns(frame, "float32")

    assert str(out["alpha101_001"].dtype) == "float32"
    assert out["alpha101_001"].isna().tolist() == [False, True, True, True]
    assert np.isinf(out["feature_num"]).tolist() == [False, True, True, False]


def test_normalize_factor_dtype_rejects_unsupported_value() -> None:
    assert normalize_factor_dtype(" FLOAT64 ") == "float64"
    with pytest.raises(ValueError, match="Unsupported factor dtype"):
        normalize_factor_dtype("float16")


def test_filter_factor_columns_preserves_non_factors_and_reports_missing_prefix() -> None:
    selected, summary = filter_factor_columns(
        ["date", "ticker", "alpha158_kmid", "alpha360_close_lag00", "feature_num"],
        include_factor_prefixes=["alpha158_"],
    )

    assert selected == ["date", "ticker", "alpha158_kmid", "feature_num"]
    assert summary["selected_factor_columns"] == 1
    assert summary["dropped_factor_columns"] == 1

    with pytest.raises(ValueError, match="alpha101_"):
        filter_factor_columns(["date", "ticker", "alpha158_kmid"], include_factor_prefixes=["alpha101"])


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
            "benchmark_next_period_return": [0.005, 0.005],
            "benchmark_cum_ret": [100.0, 100.0],
        }
    )

    with pytest.raises(KeyError, match="pred_rel_return"):
        preprocess_data(raw, label_source="pred_rel_return", apply_global_fill=False)


def test_preprocess_data_does_not_forward_fill_targets_or_state_columns() -> None:
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-31", "2021-02-28", "2021-03-31"]),
            "ticker": ["A", "A", "A"],
            "f1": [1.0, np.nan, 3.0],
            "next_period_return": [0.10, np.nan, 0.03],
            "benchmark_next_period_return": [0.01, np.nan, 0.01],
            "benchmark_cum_ret": [1.0, np.nan, 1.02],
            "is_tradable": [True, np.nan, True],
            "is_suspended": [False, np.nan, False],
            "is_st": [False, np.nan, False],
            "hit_up_limit": [False, np.nan, False],
            "hit_down_limit": [False, np.nan, False],
        }
    )

    out = preprocess_data(raw, apply_global_fill=True)
    idx = (pd.Timestamp("2021-02-28"), "A")

    assert np.isclose(float(out.loc[idx, "f1"]), 1.0)
    assert pd.isna(out.loc[idx, "next_period_return"])
    assert pd.isna(out.loc[idx, "benchmark_next_period_return"])
    assert pd.isna(out.loc[idx, "benchmark_cum_ret"])
    assert pd.isna(out.loc[idx, "is_tradable"])
    assert pd.isna(out.loc[idx, "is_suspended"])
    assert pd.isna(out.loc[idx, "is_st"])
    assert pd.isna(out.loc[idx, "hit_up_limit"])
    assert pd.isna(out.loc[idx, "hit_down_limit"])
    assert pd.isna(out.loc[idx, "rel_return"])


def test_apply_missing_feature_policy_errors_by_default_and_can_fill_for_legacy() -> None:
    frame = pd.DataFrame({"f1": [1.0]})

    with pytest.raises(ValueError, match="Missing selected feature columns"):
        apply_missing_feature_policy(
            frame,
            ["f1", "missing_factor"],
            frame_role="test frame",
            policy="error",
        )

    with pytest.warns(RuntimeWarning, match="filling with 0.0"):
        filled = apply_missing_feature_policy(
            frame,
            ["f1", "missing_factor"],
            frame_role="legacy frame",
            policy="warn_fill_zero",
        )

    assert filled["missing_factor"].tolist() == [0.0]
    assert filled.attrs["missing_feature_fallbacks"] == [
        {"frame_role": "legacy frame", "columns": ["missing_factor"]}
    ]


def test_load_market_data_unsupported_suffix_raises_value_error(tmp_path) -> None:
    bad_path = tmp_path / "sample.csv"
    bad_path.write_text("date,ticker\n2021-01-01,A\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported data format"):
        load_market_data(bad_path)


def test_load_market_data_prunes_parquet_factor_columns(tmp_path) -> None:
    data_path = tmp_path / "panel.parquet"
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-01", "2021-01-02"]),
            "ticker": ["A", "A"],
            "alpha158_kmid": [0.1, 0.2],
            "alpha360_close_lag00": [0.0, 0.0],
            "next_period_return": [0.01, 0.02],
            "benchmark_next_period_return": [0.0, 0.0],
        }
    ).to_parquet(data_path, index=False)

    out = load_market_data(data_path, include_factor_prefixes=["alpha158_"])

    assert "alpha158_kmid" in out.columns
    assert "alpha360_close_lag00" not in out.columns
    assert "next_period_return" in out.columns
    assert out.attrs["factor_selection"]["column_pruned"] is True


def test_save_market_data_defaults_to_zstd(tmp_path) -> None:
    data_path = tmp_path / "panel.parquet"
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-01"]),
            "ticker": ["A"],
            "x": [1.0],
        }
    ).set_index(["date", "ticker"])

    save_market_data(frame, data_path)

    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(data_path)
    assert DEFAULT_PARQUET_COMPRESSION == "zstd"
    assert parquet.metadata.row_group(0).column(0).compression == "ZSTD"


def test_parquet_write_options_rejects_snappy_level() -> None:
    with pytest.raises(ValueError, match="snappy"):
        parquet_write_options(compression="snappy", compression_level=3)


def test_parquet_write_options_rejects_invalid_row_group_size() -> None:
    with pytest.raises(ValueError, match="row group size"):
        parquet_write_options(row_group_size=0)


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
