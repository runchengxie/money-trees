from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from .base import BaseMarketProfile

if TYPE_CHECKING:
    from moneytree.config import BacktestSettings


class CNMarketProfile(BaseMarketProfile):
    market_id = "cn"

    @staticmethod
    def _benchmark_return_column(settings: BacktestSettings | None) -> str:
        if settings is None:
            return "benchmark_next_period_return"
        return str(settings.benchmark_return_column or "benchmark_next_period_return")

    @staticmethod
    def _benchmark_cum_column(settings: BacktestSettings | None) -> str:
        if settings is None:
            return "benchmark_cum_ret"
        return str(settings.benchmark_cum_column or "benchmark_cum_ret")

    @staticmethod
    def _tradability_columns(settings: BacktestSettings | None) -> dict[str, str]:
        if settings is None:
            return {}
        return {str(key): str(value) for key, value in settings.market_tradability_columns.items()}

    @staticmethod
    def _tradability_filters(settings: BacktestSettings | None) -> dict[str, bool]:
        if settings is None:
            return {}
        return {str(key): bool(value) for key, value in settings.market_tradability_filters.items()}

    def required_columns(
        self,
        *,
        label_source: str,
        settings: BacktestSettings | None = None,
    ) -> set[str]:
        required = {"next_period_return", "benchmark_cum_ret"}
        if label_source == "actual":
            required.add("benchmark_next_period_return")
        elif label_source == "pred_rel_return":
            required.add("pred_rel_return")
        else:
            raise ValueError(f"Unsupported label_source for market profile 'cn': {label_source}")

        tradability_columns = self._tradability_columns(settings)
        tradability_filters = self._tradability_filters(settings)
        for key, enabled in tradability_filters.items():
            if enabled:
                column = tradability_columns.get(key)
                if not column:
                    raise ValueError(
                        f"Market profile 'cn' requires a tradability column mapping for '{key}'."
                    )
                required.add(column)
        return required

    def prepare_frame(
        self,
        *,
        frame: pd.DataFrame,
        label_source: str,
        settings: BacktestSettings | None = None,
    ) -> pd.DataFrame:
        prepared = frame.copy()
        benchmark_return_column = self._benchmark_return_column(settings)
        benchmark_cum_column = self._benchmark_cum_column(settings)

        if (
            benchmark_return_column != "benchmark_next_period_return"
            and "benchmark_next_period_return" not in prepared.columns
            and benchmark_return_column in prepared.columns
        ):
            prepared["benchmark_next_period_return"] = prepared[benchmark_return_column]
        if (
            benchmark_cum_column != "benchmark_cum_ret"
            and "benchmark_cum_ret" not in prepared.columns
            and benchmark_cum_column in prepared.columns
        ):
            prepared["benchmark_cum_ret"] = prepared[benchmark_cum_column]

        self.validate_frame(frame=prepared, label_source=label_source, settings=settings)
        return prepared

    def filter_tradable_frame(
        self,
        frame: pd.DataFrame,
        *,
        settings: BacktestSettings | None = None,
    ) -> pd.DataFrame:
        if frame.empty:
            return frame

        filtered = frame
        if "is_tradable" in filtered.columns:
            filtered = filtered.loc[filtered["is_tradable"].fillna(False).astype(bool)]
        elif "tradeable" in filtered.columns:
            filtered = filtered.loc[filtered["tradeable"].fillna(False).astype(bool)]

        tradability_columns = self._tradability_columns(settings)
        tradability_filters = self._tradability_filters(settings)
        if not tradability_filters:
            return filtered

        mask = pd.Series(True, index=filtered.index, dtype=bool)
        for key, enabled in tradability_filters.items():
            if not enabled:
                continue
            column = tradability_columns[key]
            series = filtered[column].fillna(False).astype(bool)
            mask &= ~series

        return filtered.loc[mask]
