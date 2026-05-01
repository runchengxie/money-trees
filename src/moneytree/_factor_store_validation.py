from __future__ import annotations

import pandas as pd

from moneytree.data import ensure_date_ticker_index


class FactorStoreValidationError(ValueError):
    """Raised when factor-store files cannot be aligned on date/ticker."""


def _validate_unique_date_ticker(frame: pd.DataFrame, *, source_name: str) -> pd.DataFrame:
    indexed = ensure_date_ticker_index(frame)
    if indexed.index.has_duplicates:
        raise FactorStoreValidationError(f"{source_name} has duplicate date/ticker keys.")
    return indexed


def validate_factor_store_keys(
    base_frame: pd.DataFrame,
    factor_frames: dict[str, pd.DataFrame],
) -> None:
    """Validate unique and aligned date/ticker keys for factor-store frames."""
    base = _validate_unique_date_ticker(base_frame, source_name="base panel")
    for family, frame in factor_frames.items():
        factors = _validate_unique_date_ticker(frame, source_name=f"{family} factors")
        if not factors.index.equals(base.index):
            raise FactorStoreValidationError(
                f"{family} factors are not aligned with the base panel date/ticker keys."
            )
