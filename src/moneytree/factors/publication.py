from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from moneytree.data import ensure_date_ticker_index
from moneytree.factors.evaluate import compute_factor_ic, summarize_factor_ic

PUBLIC_SNAPSHOT_SCHEMA_VERSION = "1.1"
PUBLIC_SNAPSHOT_KIND = "moneytree_factor_evidence_snapshot"
_FORBIDDEN_PUBLIC_KEYS = {
    "ticker",
    "tickers",
    "positions",
    "weights",
    "portfolio_weights",
    "raw_path",
    "input_path",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _date_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def _factor_family(name: str) -> str:
    lowered = name.lower()
    for family in ("alpha101", "alpha191", "alpha158", "alpha360"):
        if family in lowered:
            return family
    return "custom"


def _group_returns(
    panel: pd.DataFrame,
    factor: str,
    return_column: str,
    group_count: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for date, group in panel.groupby(level="date", sort=True):
        values = pd.to_numeric(group[factor], errors="coerce")
        returns = pd.to_numeric(group[return_column], errors="coerce")
        valid = pd.concat([values.rename("factor"), returns.rename("return")], axis=1)
        valid = valid.replace([np.inf, -np.inf], np.nan).dropna()
        if valid.empty:
            continue
        ranks = valid["factor"].rank(method="first")
        buckets = pd.qcut(ranks, q=min(group_count, len(valid)), labels=False)
        for bucket, bucket_values in valid.assign(bucket=buckets).groupby("bucket"):
            rows.append(
                {
                    "date": date,
                    "group": int(bucket) + 1,
                    "mean_return": float(bucket_values["return"].mean()),
                }
            )

    if not rows:
        return []
    frame = pd.DataFrame(rows)
    summary = frame.groupby("group", sort=True).agg(
        mean_return=("mean_return", "mean"),
        periods=("date", "nunique"),
    )
    return [
        {
            "group": int(group),
            "mean_return": float(row["mean_return"]),
            "periods": int(row["periods"]),
        }
        for group, row in summary.iterrows()
    ]


def build_factor_evidence_snapshot(
    frame: pd.DataFrame,
    factor_columns: Iterable[str],
    *,
    return_column: str = "next_period_return",
    data_version: str = "unknown",
    config: dict[str, Any] | None = None,
    git_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an aggregate-only, JSON-safe public factor evidence snapshot."""
    required = {"date", "ticker", return_column}
    available = set(frame.columns)
    if isinstance(frame.index, pd.MultiIndex):
        available.update(name for name in frame.index.names if name is not None)
    missing = sorted(required - available)
    if missing:
        raise KeyError(f"Missing required panel columns: {missing}")

    factors = [str(factor) for factor in factor_columns]
    missing_factors = sorted(set(factors) - set(frame.columns))
    if missing_factors:
        raise KeyError(f"Missing factor columns: {missing_factors}")
    if not factors:
        raise ValueError("At least one factor column is required")

    panel = ensure_date_ticker_index(frame)
    ic_frame = compute_factor_ic(panel, factors, return_column=return_column)
    summaries = summarize_factor_ic(ic_frame).set_index("factor")
    group_count = int((config or {}).get("group_count", 5))
    if group_count < 2:
        raise ValueError("group_count must be at least 2")

    factor_payload: list[dict[str, Any]] = []
    for factor in factors:
        group = ic_frame.loc[ic_frame["factor"] == factor]
        summary = summaries.loc[factor] if factor in summaries.index else None
        valid_observations = int(group["n_obs"].sum()) if not group.empty else 0
        total_observations = int(len(panel))
        factor_payload.append(
            {
                "name": factor,
                "family": _factor_family(factor),
                "coverage": {
                    "valid_observations": valid_observations,
                    "total_observations": total_observations,
                    "ratio": (
                        float(valid_observations / total_observations)
                        if total_observations
                        else None
                    ),
                },
                "ic": {
                    "mean": summary["ic_mean"] if summary is not None else None,
                    "ir": summary["ic_ir"] if summary is not None else None,
                    "positive_rate": (
                        summary["ic_positive_rate"] if summary is not None else None
                    ),
                },
                "rank_ic": {
                    "mean": summary["rank_ic_mean"] if summary is not None else None,
                    "ir": summary["rank_ic_ir"] if summary is not None else None,
                    "positive_rate": (
                        summary["rank_ic_positive_rate"] if summary is not None else None
                    ),
                },
                "group_returns": _group_returns(panel, factor, return_column, group_count),
                "annual_slices": [],
                "regime_slices": [],
                "uncertainty": {
                    "status": "not_provided",
                    "reason": "holding_period_days_not_supplied",
                },
            }
        )

    dates = pd.to_datetime(panel.index.get_level_values("date"), errors="coerce").dropna()
    tickers = panel.index.get_level_values("ticker").nunique()
    payload = {
        "kind": PUBLIC_SNAPSHOT_KIND,
        "schema_version": PUBLIC_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_version": data_version,
        "code_revision": (git_metadata or {}).get("revision"),
        "dataset": {
            "date_start": _date_text(dates.min()) if len(dates) else None,
            "date_end": _date_text(dates.max()) if len(dates) else None,
            "trading_days": int(dates.nunique()),
            "ticker_count": int(tickers),
            "observation_count": int(len(panel)),
            "return_column": return_column,
        },
        "config": {"group_count": group_count},
        "factors": factor_payload,
        "uncertainty": {
            "status": "not_provided",
            "reason": "holding_period_days_not_supplied",
        },
        "temporal_validation": {
            "status": "not_provided",
            "reason": "temporal_slices_not_computed",
        },
        "multiple_testing": {
            "status": "not_provided",
            "reason": "holding_period_days_not_supplied",
        },
        "public_limits": [
            "Aggregate evidence only; no ticker-level values or portfolio weights.",
            "Evidence is descriptive research output and is not a return guarantee.",
        ],
    }
    return _json_safe(payload)


def audit_public_snapshot(payload: dict[str, Any]) -> None:
    """Reject public payloads containing forbidden private or non-JSON values."""

    def visit(value: Any, path: str = "snapshot") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in _FORBIDDEN_PUBLIC_KEYS:
                    raise ValueError(f"Forbidden public field: {path}.{key}")
                visit(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
        elif isinstance(value, float):
            if not np.isfinite(value):
                raise ValueError(f"Non-finite public value: {path}")
        elif isinstance(value, str) and (
            value.startswith("/") or (len(value) > 2 and value[1:3] == ":\\")
        ):
            raise ValueError(f"Absolute path in public payload: {path}")

    visit(payload)
