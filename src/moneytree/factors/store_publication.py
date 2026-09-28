from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from moneytree._factor_store_manifest import _part_metadata_by_path, read_factor_store_manifest
from moneytree.data import ensure_date_ticker_index
from moneytree.factors.publication import (
    PUBLIC_SNAPSHOT_KIND,
    PUBLIC_SNAPSHOT_SCHEMA_VERSION,
    _factor_family,
    _json_safe,
    audit_public_snapshot,
)


def _selected_families(manifest: dict[str, Any], families: Iterable[str] | None) -> list[str]:
    available = list(manifest.get("factor_families", {}))
    if families is None:
        return available
    requested = [str(item).strip().lower().replace("-", "_") for item in families]
    selected = [family for family in requested if family]
    unknown = sorted(set(selected).difference(available))
    if unknown:
        raise KeyError(f"Factor families are not in the store: {unknown}")
    if not selected:
        raise ValueError("At least one factor family is required")
    return list(dict.fromkeys(selected))


def _part_in_range(
    part: dict[str, Any], date_start: pd.Timestamp | None, date_end: pd.Timestamp | None
) -> bool:
    start = pd.Timestamp(part["start_date"]) if part.get("start_date") else None
    end = pd.Timestamp(part["end_date"]) if part.get("end_date") else None
    return not (
        date_start is not None
        and end is not None
        and end < date_start
        or date_end is not None
        and start is not None
        and start > date_end
    )


def _corr_columns(values: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Return Pearson correlations for columns with NaN values."""
    valid = np.isfinite(values) & np.isfinite(target)[:, None]
    count = valid.sum(axis=0).astype(float)
    value_sum = np.where(valid, values, 0.0).sum(axis=0)
    value_mean = np.divide(value_sum, count, out=np.zeros_like(value_sum), where=count > 0)
    target_count = float(np.isfinite(target).sum())
    target_mean = float(np.where(np.isfinite(target), target, 0.0).sum() / target_count)
    centered_values = np.where(valid, values - value_mean, 0.0)
    centered_target = np.where(np.isfinite(target), target - target_mean, 0.0)
    numerator = (centered_values * centered_target[:, None]).sum(axis=0)
    value_scale = np.sqrt((centered_values**2).sum(axis=0))
    target_scale = np.sqrt((centered_target**2).sum())
    denominator = value_scale * target_scale
    result = np.full(values.shape[1], np.nan, dtype=float)
    usable = (count >= 2) & (denominator > 0)
    result[usable] = numerator[usable] / denominator[usable]
    return result


def _rank_columns(values: np.ndarray) -> np.ndarray:
    return pd.DataFrame(values).rank(method="average", na_option="keep").to_numpy(dtype=float)


def _update_chunk(
    factor_frame: pd.DataFrame,
    returns: pd.Series,
    *,
    group_count: int,
    sums: dict[str, dict[str, float]],
    counts: dict[str, dict[str, int]],
    ic_values: dict[str, list[float]],
    rank_ic_values: dict[str, list[float]],
    valid_counts: dict[str, int],
    total_observations: dict[str, int],
    dates_seen: set[pd.Timestamp],
    tickers_seen: set[str],
) -> None:
    indexed = ensure_date_ticker_index(factor_frame)
    target = pd.to_numeric(returns.reindex(indexed.index), errors="coerce").to_numpy(dtype=float)
    factor_names = [str(column) for column in indexed.columns]
    values = indexed.to_numpy(dtype=float)
    dates = pd.to_datetime(indexed.index.get_level_values("date"))
    tickers_seen.update(str(value) for value in indexed.index.get_level_values("ticker").unique())
    for date in pd.Index(dates).unique():
        mask = dates == date
        date_values = values[mask]
        date_target = target[mask]
        valid_target = np.isfinite(date_target)
        if not valid_target.any():
            continue
        dates_seen.add(pd.Timestamp(date))
        ic = _corr_columns(date_values, date_target)
        ranked_values = _rank_columns(date_values)
        ranked_target = pd.Series(date_target).rank(method="average", na_option="keep").to_numpy()
        rank_ic = _corr_columns(ranked_values, ranked_target)
        for position, factor in enumerate(factor_names):
            valid = np.isfinite(date_values[:, position]) & valid_target
            valid_count = int(valid.sum())
            total_observations[factor] += int(len(date_target))
            valid_counts[factor] += valid_count
            if np.isfinite(ic[position]):
                ic_values[factor].append(float(ic[position]))
            if np.isfinite(rank_ic[position]):
                rank_ic_values[factor].append(float(rank_ic[position]))
            if valid_count < 2:
                continue
            factor_values = date_values[valid, position]
            factor_returns = date_target[valid]
            ranks = pd.Series(factor_values).rank(method="first").to_numpy()
            bucket = np.minimum(
                group_count - 1,
                ((ranks - 1) * group_count / len(ranks)).astype(int),
            )
            for group in range(group_count):
                selected = bucket == group
                if selected.any():
                    key = str(group + 1)
                    sums[factor][key] += float(factor_returns[selected].mean())
                    counts[factor][key] += 1


def build_factor_evidence_snapshot_from_store(
    manifest_path: str | Path,
    *,
    families: Iterable[str] | None = None,
    date_start: object | None = None,
    date_end: object | None = None,
    return_column: str = "next_period_return",
    data_version: str = "unknown",
    group_count: int = 5,
    code_revision: str | None = None,
) -> dict[str, Any]:
    """Build a public snapshot by reading a partitioned factor store incrementally."""
    if group_count < 2:
        raise ValueError("group_count must be at least 2")
    manifest_file = Path(manifest_path)
    manifest = read_factor_store_manifest(manifest_file)
    selected = _selected_families(manifest, families)
    root = manifest_file.parent
    base_path = root / str(manifest["base_panel"]["path"])
    start = pd.Timestamp(date_start) if date_start else None
    end = pd.Timestamp(date_end) if date_end else None

    sums: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    ic_values: dict[str, list[float]] = defaultdict(list)
    rank_ic_values: dict[str, list[float]] = defaultdict(list)
    valid_counts: dict[str, int] = defaultdict(int)
    total_observations: dict[str, int] = defaultdict(int)
    dates_seen: set[pd.Timestamp] = set()
    tickers_seen: set[str] = set()
    factor_names: list[str] = []
    observation_count = 0
    registered_families: set[str] = set()

    for family in selected:
        entry = manifest["factor_families"][family]
        parts = _part_metadata_by_path(entry)
        for relative_path in entry.get("paths", []):
            part = parts.get(str(relative_path), {})
            if not _part_in_range(part, start, end):
                continue
            factor_path = root / str(relative_path)
            factor_frame = ensure_date_ticker_index(pd.read_parquet(factor_path))
            if start is not None or end is not None:
                dates = pd.to_datetime(factor_frame.index.get_level_values("date"))
                keep = np.ones(len(factor_frame), dtype=bool)
                if start is not None:
                    keep &= dates >= start
                if end is not None:
                    keep &= dates <= end
                factor_frame = factor_frame.loc[keep]
            if factor_frame.empty:
                continue
            current_factor_names = [str(column) for column in factor_frame.columns]
            if family not in registered_families:
                if any(name in factor_names for name in current_factor_names):
                    raise ValueError("Selected factor families contain duplicate factor columns")
                factor_names.extend(current_factor_names)
                registered_families.add(family)
            if family == selected[0]:
                observation_count += len(factor_frame)
            first_date = factor_frame.index.get_level_values("date").min()
            last_date = factor_frame.index.get_level_values("date").max()
            base_frame = pd.read_parquet(
                base_path,
                columns=[return_column],
                filters=[
                    ("date", ">=", pd.Timestamp(first_date)),
                    ("date", "<=", pd.Timestamp(last_date)),
                ],
            )
            base_frame = ensure_date_ticker_index(base_frame)
            _update_chunk(
                factor_frame,
                base_frame[return_column],
                group_count=group_count,
                sums=sums,
                counts=counts,
                ic_values=ic_values,
                rank_ic_values=rank_ic_values,
                valid_counts=valid_counts,
                total_observations=total_observations,
                dates_seen=dates_seen,
                tickers_seen=tickers_seen,
            )

    if not factor_names:
        raise ValueError("No factor partitions match the requested range")

    factor_payload: list[dict[str, Any]] = []
    for factor in factor_names:
        ic = np.asarray(ic_values[factor], dtype=float)
        rank_ic = np.asarray(rank_ic_values[factor], dtype=float)

        def metric(values: np.ndarray) -> dict[str, float | None]:
            mean = float(values.mean()) if len(values) else None
            std = float(values.std(ddof=0)) if len(values) else None
            return {
                "mean": mean,
                "ir": float(mean / std) if mean is not None and std else None,
                "positive_rate": float((values > 0).mean()) if len(values) else None,
            }

        factor_payload.append(
            {
                "name": factor,
                "family": _factor_family(factor),
                "coverage": {
                    "valid_observations": valid_counts[factor],
                    "total_observations": total_observations[factor],
                    "ratio": (
                        valid_counts[factor] / total_observations[factor]
                        if total_observations[factor]
                        else None
                    ),
                },
                "ic": metric(ic),
                "rank_ic": metric(rank_ic),
                "group_returns": [
                    {
                        "group": int(group),
                        "mean_return": sums[factor][str(group)] / counts[factor][str(group)]
                        if counts[factor][str(group)]
                        else None,
                        "periods": counts[factor][str(group)],
                    }
                    for group in range(1, group_count + 1)
                ],
            }
        )

    payload = {
        "kind": PUBLIC_SNAPSHOT_KIND,
        "schema_version": PUBLIC_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "data_version": data_version,
        "code_revision": code_revision,
        "dataset": {
            "date_start": min(dates_seen).date().isoformat() if dates_seen else None,
            "date_end": max(dates_seen).date().isoformat() if dates_seen else None,
            "trading_days": len(dates_seen),
            "ticker_count": len(tickers_seen),
            "observation_count": observation_count,
            "return_column": return_column,
        },
        "config": {"group_count": group_count, "source": "partitioned_factor_store"},
        "factors": factor_payload,
        "public_limits": [
            "Aggregate evidence only; no ticker-level values or portfolio weights.",
            "Evidence is descriptive research output and is not a return guarantee.",
        ],
    }
    result = _json_safe(payload)
    audit_public_snapshot(result)
    return result
