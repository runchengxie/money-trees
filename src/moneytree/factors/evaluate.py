from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from moneytree.data import ensure_date_ticker_index


def _safe_corr(left: pd.Series, right: pd.Series, method: str) -> float:
    aligned = pd.concat([left.rename("factor"), right.rename("target")], axis=1).dropna()
    if len(aligned) < 2:
        return float("nan")
    if aligned["factor"].nunique() < 2 or aligned["target"].nunique() < 2:
        return float("nan")
    value = aligned["factor"].corr(aligned["target"], method=method)
    return float(value) if pd.notna(value) else float("nan")


def compute_factor_ic(
    frame: pd.DataFrame,
    factor_columns: Iterable[str],
    *,
    return_column: str = "next_period_return",
) -> pd.DataFrame:
    """Compute daily cross-sectional IC and RankIC for factor columns."""
    panel = ensure_date_ticker_index(frame)
    if return_column not in panel.columns:
        raise KeyError(f"Missing return column: {return_column}")

    rows: list[dict[str, object]] = []
    for date, group in panel.groupby(level="date", sort=True):
        target = group[return_column].astype(float)
        for factor in factor_columns:
            if factor not in group.columns:
                raise KeyError(f"Missing factor column: {factor}")
            signal = group[factor].astype(float)
            valid = pd.concat([signal, target], axis=1).dropna()
            rows.append(
                {
                    "date": pd.Timestamp(date),
                    "factor": factor,
                    "ic": _safe_corr(signal, target, method="pearson"),
                    "rank_ic": _safe_corr(signal, target, method="spearman"),
                    "n_obs": int(len(valid)),
                    "coverage": float(len(valid) / len(group)) if len(group) else float("nan"),
                }
            )
    return pd.DataFrame(rows)


def summarize_factor_ic(ic_frame: pd.DataFrame) -> pd.DataFrame:
    """Summarize factor IC diagnostics by factor."""
    required = {"factor", "ic", "rank_ic", "coverage"}
    missing = required.difference(ic_frame.columns)
    if missing:
        raise KeyError(f"Missing IC columns: {sorted(missing)}")

    rows: list[dict[str, object]] = []
    for factor, group in ic_frame.groupby("factor", sort=True):
        ic = group["ic"].dropna().astype(float)
        rank_ic = group["rank_ic"].dropna().astype(float)
        ic_std = float(ic.std(ddof=0)) if len(ic) else float("nan")
        rank_std = float(rank_ic.std(ddof=0)) if len(rank_ic) else float("nan")
        rows.append(
            {
                "factor": factor,
                "ic_mean": float(ic.mean()) if len(ic) else float("nan"),
                "ic_ir": float(ic.mean() / ic_std) if ic_std and np.isfinite(ic_std) else float("nan"),
                "rank_ic_mean": float(rank_ic.mean()) if len(rank_ic) else float("nan"),
                "rank_ic_ir": (
                    float(rank_ic.mean() / rank_std)
                    if rank_std and np.isfinite(rank_std)
                    else float("nan")
                ),
                "ic_positive_rate": float((ic > 0).mean()) if len(ic) else float("nan"),
                "rank_ic_positive_rate": (
                    float((rank_ic > 0).mean()) if len(rank_ic) else float("nan")
                ),
                "avg_coverage": float(group["coverage"].mean()),
                "periods": int(len(group)),
            }
        )
    return pd.DataFrame(rows).sort_values("rank_ic_mean", ascending=False)
