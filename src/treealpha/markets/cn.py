from __future__ import annotations

import pandas as pd

from .base import BaseMarketProfile


class CNMarketProfile(BaseMarketProfile):
    market_id = "cn"

    def _raise_placeholder(self) -> None:
        raise NotImplementedError(
            "Market profile 'cn' is a template placeholder. Replace "
            "src/treealpha/markets/cn.py with your A-share data contract before running."
        )

    def required_columns(self, *, label_source: str) -> set[str]:
        self._raise_placeholder()

    def prepare_frame(self, *, frame: pd.DataFrame, label_source: str) -> pd.DataFrame:
        self._raise_placeholder()

    def filter_tradable_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        self._raise_placeholder()
