from __future__ import annotations

from pathlib import Path
from typing import Iterable, Literal

import numpy as np
import pandas as pd

LabelSource = Literal["actual", "pred_rel_return"]

NON_FEATURE_COLUMNS = {
    "date",
    "ticker",
    "return",
    "cum_ret",
    "spy_cum_ret",
    "next_period_return",
    "spy_next_period_return",
    "pred_rel_return",
    "rel_return",
    "rel_performance",
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


def compute_relative_return(frame: pd.DataFrame, label_source: LabelSource) -> pd.Series:
    """Compute the relative return used for label generation."""
    if label_source == "actual":
        required = {"next_period_return", "spy_next_period_return"}
        missing = required.difference(frame.columns)
        if missing:
            raise KeyError(f"Missing required columns for actual labels: {sorted(missing)}")
        rel = frame["next_period_return"] - frame["spy_next_period_return"]
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


def preprocess_data(
    frame: pd.DataFrame,
    label_source: LabelSource = "actual",
    label_threshold: float = 0.05,
    add_missing_indicators: bool = False,
) -> pd.DataFrame:
    """
    Clean the dataset and build labels.

    Steps:
    1) inf -> NaN
    2) ticker-level forward fill
    3) numeric median fill / bool False fill / object "missing" fill
    4) optional missing-indicator columns
    5) rel_return + rel_performance labels
    """
    data = ensure_date_ticker_index(frame)
    data = data.replace([np.inf, -np.inf], np.nan)

    data = data.groupby(level="ticker", sort=False).ffill()
    missing_mask = data.isna()

    numeric_cols = data.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) > 0:
        medians = data[numeric_cols].median()
        data[numeric_cols] = data[numeric_cols].fillna(medians)

    bool_cols = data.select_dtypes(include=["bool"]).columns
    if len(bool_cols) > 0:
        data[bool_cols] = data[bool_cols].fillna(False)

    object_cols = data.select_dtypes(include=["object"]).columns
    if len(object_cols) > 0:
        data[object_cols] = data[object_cols].fillna("missing")

    if add_missing_indicators:
        for col in numeric_cols:
            if missing_mask[col].any():
                data[f"{col}__is_missing"] = missing_mask[col].astype(np.int8)

    rel_return = compute_relative_return(data, label_source=label_source)
    rel_labels = make_labels(rel_return, threshold=label_threshold)
    labels_frame = pd.DataFrame(
        {"rel_return": rel_return, "rel_performance": rel_labels},
        index=data.index,
    )
    data = pd.concat([data.copy(), labels_frame], axis=1)
    return data


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


def build_xy_returns(
    frame: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Build model matrix, labels and realized next-period returns."""
    features = frame[feature_columns].copy()
    bool_cols = features.select_dtypes(include=["bool"]).columns
    if len(bool_cols) > 0:
        features[bool_cols] = features[bool_cols].astype(np.int8)

    labels = frame["rel_performance"].to_numpy()
    realized_returns = frame["next_period_return"].to_numpy()
    return features, labels, realized_returns


def build_spy_series(frame: pd.DataFrame) -> pd.Series:
    """Build a unique-date SPY cumulative return series."""
    compact = frame.loc[:, ["spy_cum_ret"]].copy()
    spy = (
        compact.reset_index()[["date", "spy_cum_ret"]]
        .drop_duplicates(subset=["date"])
        .set_index("date")
        .sort_index()["spy_cum_ret"]
    )
    return spy
