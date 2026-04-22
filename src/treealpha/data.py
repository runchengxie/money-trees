from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from typing import Iterable, Literal

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from treealpha.config import BacktestSettings
    from treealpha.markets.base import BaseMarketProfile

LabelSource = Literal["actual", "pred_rel_return"]

NON_FEATURE_COLUMNS = {
    "date",
    "ticker",
    "return",
    "cum_ret",
    "benchmark_cum_ret",
    "benchmark_next_period_return",
    "spy_cum_ret",
    "next_period_return",
    "spy_next_period_return",
    "pred_rel_return",
    "rel_return",
    "rel_performance",
    "is_tradable",
    "tradeable",
}


def load_market_data(path: str | Path) -> pd.DataFrame:
    """Load market data from a pickle/parquet file."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix in {".pkl", ".pickle"}:
        return pd.read_pickle(file_path)
    if suffix == ".parquet":
        return pd.read_parquet(file_path)
    raise ValueError(f"Unsupported data format: {file_path}")


def save_market_data(
    frame: pd.DataFrame,
    path: str | Path,
    compression: str = "snappy",
) -> None:
    """Persist market data as parquet."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(file_path, compression=compression, index=True)


def ensure_date_ticker_index(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy indexed by ('date', 'ticker') and sorted by date."""
    out = frame.copy()

    if isinstance(out.index, pd.MultiIndex) and {"date", "ticker"}.issubset(
        set(out.index.names)
    ):
        if out.index.names != ["date", "ticker"]:
            out = out.reorder_levels(["date", "ticker"])
    elif {"date", "ticker"}.issubset(out.columns):
        out = out.set_index(["date", "ticker"])
    else:
        raise ValueError("Data must contain date/ticker index or date/ticker columns.")

    out = out.sort_index(level=["date", "ticker"])
    return out


def _resolve_benchmark_return_column(frame: pd.DataFrame) -> str:
    for column in ("benchmark_next_period_return", "spy_next_period_return"):
        if column in frame.columns:
            return column
    raise KeyError(
        "Missing required benchmark return column. Expected one of "
        "['benchmark_next_period_return', 'spy_next_period_return']"
    )


def _resolve_benchmark_cum_column(frame: pd.DataFrame) -> str:
    for column in ("benchmark_cum_ret", "spy_cum_ret"):
        if column in frame.columns:
            return column
    raise KeyError(
        "Missing required benchmark cumulative column. Expected one of "
        "['benchmark_cum_ret', 'spy_cum_ret']"
    )


def compute_relative_return(frame: pd.DataFrame, label_source: LabelSource) -> pd.Series:
    """Compute the relative return used for label generation."""
    if label_source == "actual":
        benchmark_return_col = _resolve_benchmark_return_column(frame)
        required = {"next_period_return", benchmark_return_col}
        missing = required.difference(frame.columns)
        if missing:
            raise KeyError(f"Missing required columns for actual labels: {sorted(missing)}")
        rel = frame["next_period_return"] - frame[benchmark_return_col]
        rel.name = "rel_return"
        return rel

    if "pred_rel_return" not in frame.columns:
        raise KeyError("Missing required column for pred_rel_return labels: pred_rel_return")
    rel = frame["pred_rel_return"].copy()
    rel.name = "rel_return"
    return rel


def make_labels(relative_returns: pd.Series, threshold: float = 0.05) -> pd.Series:
    """Map relative returns into {-1, 0, +1} labels."""
    labels = np.zeros(len(relative_returns), dtype=np.int8)
    labels[relative_returns > threshold] = 1
    labels[relative_returns < -threshold] = -1
    return pd.Series(labels, index=relative_returns.index, name="rel_performance")


def fill_missing_with_reference(
    frame: pd.DataFrame,
    reference: pd.DataFrame,
    add_missing_indicators: bool = False,
) -> pd.DataFrame:
    """
    Fill missing values in `frame` using statistics fit on `reference`.

    Numeric columns are median-filled, bool columns are False-filled, and object columns are
    filled with "missing". This allows train-window fit / valid-test transform workflows.
    """
    data = frame.copy()
    ref = reference.copy()
    missing_mask = data.isna()

    numeric_cols = list(ref.select_dtypes(include=[np.number]).columns)
    shared_numeric = [c for c in numeric_cols if c in data.columns]
    if shared_numeric:
        medians = ref[shared_numeric].median()
        data[shared_numeric] = data[shared_numeric].fillna(medians)

    bool_cols = list(ref.select_dtypes(include=["bool"]).columns)
    shared_bool = [c for c in bool_cols if c in data.columns]
    if shared_bool:
        data[shared_bool] = data[shared_bool].fillna(False)

    object_cols = [
        c
        for c in ref.columns
        if pd.api.types.is_object_dtype(ref[c]) or pd.api.types.is_string_dtype(ref[c])
    ]
    shared_object = [c for c in object_cols if c in data.columns]
    if shared_object:
        data[shared_object] = data[shared_object].fillna("missing")

    if add_missing_indicators:
        for col in shared_numeric:
            if ref[col].isna().any():
                data[f"{col}__is_missing"] = missing_mask[col].astype(np.int8)

    return data


def preprocess_data(
    frame: pd.DataFrame,
    market_profile: "BaseMarketProfile | None" = None,
    label_source: LabelSource = "actual",
    label_threshold: float = 0.05,
    add_missing_indicators: bool = False,
    apply_global_fill: bool = True,
    settings: "BacktestSettings | None" = None,
) -> pd.DataFrame:
    """
    Clean the dataset and build labels.

    Steps:
    1) inf -> NaN
    2) ticker-level forward fill
    3) optional numeric median fill / bool False fill / object "missing" fill
    4) optional missing-indicator columns
    5) rel_return + rel_performance labels
    """
    prepared_frame = (
        market_profile.prepare_frame(frame=frame, label_source=label_source, settings=settings)
        if market_profile is not None
        else frame
    )
    data = ensure_date_ticker_index(prepared_frame)
    data = data.replace([np.inf, -np.inf], np.nan)

    data = data.groupby(level="ticker", sort=False).ffill()
    if apply_global_fill:
        data = fill_missing_with_reference(
            frame=data,
            reference=data,
            add_missing_indicators=add_missing_indicators,
        )

    rel_return = compute_relative_return(data, label_source=label_source)
    rel_labels = make_labels(rel_return, threshold=label_threshold)
    labels_frame = pd.DataFrame(
        {"rel_return": rel_return, "rel_performance": rel_labels},
        index=data.index,
    )
    data = pd.concat([data.copy(), labels_frame], axis=1)
    return data


def apply_feature_lag(
    frame: pd.DataFrame,
    feature_columns: Iterable[str],
    lag_periods: int,
    drop_all_missing_rows: bool = True,
) -> pd.DataFrame:
    """
    Apply an extra per-ticker lag to model features.

    This is useful for leakage-sensitivity checks (e.g., shift=1/2 style experiments).
    """
    if lag_periods <= 0:
        return frame.copy()
    if not isinstance(frame.index, pd.MultiIndex) or "ticker" not in frame.index.names:
        raise ValueError("apply_feature_lag expects a ('date', 'ticker') MultiIndex frame.")

    cols = [col for col in feature_columns if col in frame.columns]
    if not cols:
        return frame.copy()

    out = frame.copy()
    shifted = out[cols].groupby(level="ticker", sort=False).shift(int(lag_periods))
    out.loc[:, cols] = shifted

    if drop_all_missing_rows:
        valid_mask = out[cols].notna().any(axis=1)
        out = out.loc[valid_mask]

    return out


def slice_by_date(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Inclusive date slice on a ('date', 'ticker') indexed frame."""
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    date_index = frame.index.get_level_values("date")
    mask = (date_index >= start_ts) & (date_index <= end_ts)
    return frame.loc[mask]


def get_feature_columns(
    frame: pd.DataFrame,
    extra_drop: Iterable[str] | None = None,
) -> list[str]:
    """Return model feature columns (numeric and bool only)."""
    drop_cols = set(NON_FEATURE_COLUMNS)
    if extra_drop is not None:
        drop_cols.update(extra_drop)

    candidate = [c for c in frame.columns if c not in drop_cols]
    numeric_or_bool = frame[candidate].select_dtypes(include=[np.number, "bool"]).columns
    return list(numeric_or_bool)


def build_xy_target_returns(
    frame: pd.DataFrame,
    feature_columns: list[str],
    target_column: str = "rel_performance",
    realized_return_column: str = "next_period_return",
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Build model matrix, configured target, and realized next-period returns."""
    features = frame[feature_columns].copy()
    bool_cols = features.select_dtypes(include=["bool"]).columns
    if len(bool_cols) > 0:
        features[bool_cols] = features[bool_cols].astype(np.int8)

    if target_column not in frame.columns:
        raise KeyError(f"Missing target column: {target_column}")
    if realized_return_column not in frame.columns:
        raise KeyError(f"Missing realized return column: {realized_return_column}")

    target = frame[target_column].to_numpy()
    realized_returns = frame[realized_return_column].to_numpy()
    return features, target, realized_returns


def build_xy_returns(
    frame: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Build model matrix, labels and realized next-period returns."""
    return build_xy_target_returns(
        frame=frame,
        feature_columns=feature_columns,
        target_column="rel_performance",
        realized_return_column="next_period_return",
    )


def build_benchmark_series(
    frame: pd.DataFrame,
    benchmark_cum_col: str | None = None,
) -> pd.Series:
    """Build a unique-date benchmark cumulative return series."""
    resolved_col = benchmark_cum_col or _resolve_benchmark_cum_column(frame)
    compact = frame.loc[:, [resolved_col]].copy()
    benchmark = (
        compact.reset_index()[["date", resolved_col]]
        .drop_duplicates(subset=["date"])
        .set_index("date")
        .sort_index()[resolved_col]
    )
    benchmark.name = resolved_col
    return benchmark


def build_spy_series(frame: pd.DataFrame) -> pd.Series:
    """Build a unique-date SPY cumulative return series."""
    return build_benchmark_series(frame=frame, benchmark_cum_col="spy_cum_ret")
