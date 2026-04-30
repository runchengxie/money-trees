from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from moneytree.config import BacktestSettings


class BaseMarketProfile(ABC):
    market_id: str

    @abstractmethod
    def required_columns(
        self,
        *,
        label_source: str,
        settings: BacktestSettings | None = None,
    ) -> set[str]:
        raise NotImplementedError

    def validate_frame(
        self,
        *,
        frame: pd.DataFrame,
        label_source: str,
        settings: BacktestSettings | None = None,
    ) -> None:
        missing = sorted(
            self.required_columns(label_source=label_source, settings=settings).difference(frame.columns)
        )
        if missing:
            raise ValueError(
                f"Market profile '{self.market_id}' is missing required columns: {missing}"
            )

    @abstractmethod
    def prepare_frame(
        self,
        *,
        frame: pd.DataFrame,
        label_source: str,
        settings: BacktestSettings | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError

    def filter_tradable_frame(
        self,
        frame: pd.DataFrame,
        *,
        settings: BacktestSettings | None = None,
    ) -> pd.DataFrame:
        return frame
