from __future__ import annotations

import pandas as pd

from .base import BaseMarketProfile


class USMarketProfile(BaseMarketProfile):
    market_id = "us"

    def required_columns(self, *, label_source: str) -> set[str]:
        required = {"next_period_return", "spy_cum_ret"}
        if label_source == "actual":
            required.add("spy_next_period_return")
        elif label_source == "pred_rel_return":
            required.add("pred_rel_return")
        else:
            raise ValueError(f"Unsupported label_source for market profile 'us': {label_source}")
        return required

    def prepare_frame(self, *, frame: pd.DataFrame, label_source: str) -> pd.DataFrame:
        self.validate_frame(frame=frame, label_source=label_source)
        prepared = frame.copy()
        if "benchmark_next_period_return" not in prepared.columns and "spy_next_period_return" in prepared.columns:
            prepared["benchmark_next_period_return"] = prepared["spy_next_period_return"]
        if "benchmark_cum_ret" not in prepared.columns and "spy_cum_ret" in prepared.columns:
            prepared["benchmark_cum_ret"] = prepared["spy_cum_ret"]
        return prepared

    def filter_tradable_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if "is_tradable" in frame.columns:
            return frame.loc[frame["is_tradable"].astype(bool)]
        if "tradeable" in frame.columns:
            return frame.loc[frame["tradeable"].astype(bool)]
        return frame
