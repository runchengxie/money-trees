from __future__ import annotations

from typing import TYPE_CHECKING

from strategy.data import (  # noqa: F401
    NON_FEATURE_COLUMNS,
    apply_feature_lag,
    build_benchmark_series,
    build_xy_returns,
    build_xy_target_returns,
    compute_relative_return,
    ensure_date_ticker_index,
    fill_missing_with_reference,
    get_feature_columns,
    load_market_data,
    make_labels,
    preprocess_data as _preprocess_data,
    save_market_data,
    slice_by_date,
)

if TYPE_CHECKING:
    from treealpha.markets.base import BaseMarketProfile


def preprocess_data(
    frame,
    *,
    market_profile: "BaseMarketProfile | None" = None,
    label_source: str = "actual",
    label_threshold: float = 0.05,
    add_missing_indicators: bool = False,
    apply_global_fill: bool = True,
):
    prepared = (
        market_profile.prepare_frame(frame=frame, label_source=label_source)
        if market_profile is not None
        else frame
    )
    return _preprocess_data(
        prepared,
        label_source=label_source,
        label_threshold=label_threshold,
        add_missing_indicators=add_missing_indicators,
        apply_global_fill=apply_global_fill,
    )
