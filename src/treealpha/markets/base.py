from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseMarketProfile(ABC):
    market_id: str

    @abstractmethod
    def required_columns(self, *, label_source: str) -> set[str]:
        raise NotImplementedError

    def validate_frame(self, *, frame: pd.DataFrame, label_source: str) -> None:
        missing = sorted(self.required_columns(label_source=label_source).difference(frame.columns))
        if missing:
            raise ValueError(
                f"Market profile '{self.market_id}' is missing required columns: {missing}"
            )

    @abstractmethod
    def prepare_frame(self, *, frame: pd.DataFrame, label_source: str) -> pd.DataFrame:
        raise NotImplementedError

    def filter_tradable_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        return frame
