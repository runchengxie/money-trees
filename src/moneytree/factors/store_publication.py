from __future__ import annotations

import io
import json
import shutil
import tarfile
import tempfile
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
    TemporalSliceAccumulator,
    _factor_family,
    _inference_fields,
    _json_safe,
    audit_public_snapshot,
    validate_benchmark_source,
)

SIGNAL_QUALITY_SCHEMA_VERSION = "1.0"


class _TarMemberFile(io.RawIOBase):
    """Seekable read-only view over one member of an uncompressed tar archive."""

    def __init__(self, archive_path: Path, offset: int, size: int) -> None:
        self._file = archive_path.open("rb")
        self._offset = offset
        self._size = size
        self._position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self._size - self._position
        size = min(size, self._size - self._position)
        if size <= 0:
            return b""
        self._file.seek(self._offset + self._position)
        data = self._file.read(size)
        self._position += len(data)
        return data

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self._position + offset
        elif whence == io.SEEK_END:
            position = self._size + offset
        else:
            raise ValueError(f"Unsupported seek mode: {whence}")
        if position < 0:
            raise ValueError("Cannot seek before the tar member")
        self._position = min(position, self._size)
        return self._position

    def tell(self) -> int:
        return self._position

    def close(self) -> None:
        if not self.closed:
            self._file.close()
        super().close()


def _read_tar_parquet(archive_path: Path, member: tarfile.TarInfo, **kwargs: Any) -> pd.DataFrame:
    if member.offset_data is None:
        raise ValueError(f"Tar member has no data offset: {member.name}")
    with _TarMemberFile(archive_path, member.offset_data, member.size) as raw:
        # PyArrow's dataset reader requires a native seekable file. Copy only
        # the requested member to a temporary file; the multi-gigabyte archive
        # itself is never unpacked.
        with tempfile.NamedTemporaryFile(suffix=".parquet") as temporary:
            shutil.copyfileobj(raw, temporary, length=1024 * 1024)
            temporary.flush()
            return pd.read_parquet(temporary.name, **kwargs)


def _archive_manifest(
    archive_path: Path,
) -> tuple[dict[str, Any], dict[str, tarfile.TarInfo], str]:
    try:
        archive = tarfile.open(archive_path, mode="r:")
    except tarfile.ReadError as exc:
        raise ValueError("Archive factor-store input must be an uncompressed tar file") from exc
    with archive:
        members = {
            member.name.lstrip("./"): member
            for member in archive.getmembers()
            if member.isfile()
        }
        manifest_paths = [name for name in members if name.endswith("/manifest.json")]
        if not manifest_paths:
            raise ValueError("Archive does not contain a factor-store manifest.json")
        manifest_name = manifest_paths[0]
        manifest = json.loads(archive.extractfile(members[manifest_name]).read())
        if manifest.get("kind") != "moneytree_factor_store":
            raise ValueError("Archive manifest is not a moneytree factor store")
        prefix = manifest_name[: -len("manifest.json")]
        return manifest, members, prefix


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
    """Return Pearson correlations using the valid value/target pairs in each column."""
    target_columns = np.broadcast_to(target[:, None], values.shape) if target.ndim == 1 else target
    valid = np.isfinite(values) & np.isfinite(target_columns)
    count = valid.sum(axis=0).astype(float)
    value_sum = np.where(valid, values, 0.0).sum(axis=0)
    value_mean = np.divide(value_sum, count, out=np.zeros_like(value_sum), where=count > 0)
    target_sum = np.where(valid, target_columns, 0.0).sum(axis=0)
    target_mean = np.divide(target_sum, count, out=np.zeros_like(target_sum), where=count > 0)
    centered_values = np.where(valid, values - value_mean, 0.0)
    centered_target = np.where(valid, target_columns - target_mean, 0.0)
    numerator = (centered_values * centered_target).sum(axis=0)
    value_scale = np.sqrt((centered_values**2).sum(axis=0))
    target_scale = np.sqrt((centered_target**2).sum(axis=0))
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
    temporal_accumulator: TemporalSliceAccumulator | None = None,
    rank_ic_series: dict[str, list[float]] | None = None,
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
            if rank_ic_series is not None:
                for factor in factor_names:
                    rank_ic_series[factor].append(float("nan"))
            continue
        dates_seen.add(pd.Timestamp(date))
        ic = _corr_columns(date_values, date_target)
        valid_pairs = np.isfinite(date_values) & valid_target[:, None]
        ranked_values = _rank_columns(np.where(valid_pairs, date_values, np.nan))
        ranked_target = _rank_columns(np.where(valid_pairs, date_target[:, None], np.nan))
        rank_ic = _corr_columns(ranked_values, ranked_target)
        day_rank_ic: dict[str, float] = {}
        day_group_returns: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for position, factor in enumerate(factor_names):
            valid = np.isfinite(date_values[:, position]) & valid_target
            valid_count = int(valid.sum())
            total_observations[factor] += int(len(date_target))
            valid_counts[factor] += valid_count
            if np.isfinite(ic[position]):
                ic_values[factor].append(float(ic[position]))
            if np.isfinite(rank_ic[position]):
                rank_ic_values[factor].append(float(rank_ic[position]))
                day_rank_ic[factor] = float(rank_ic[position])
            else:
                day_rank_ic[factor] = float("nan")
            if rank_ic_series is not None:
                rank_ic_series[factor].append(day_rank_ic[factor])
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
                    day_group_returns[factor].append(
                        {"group": group + 1, "mean_return": float(factor_returns[selected].mean())}
                    )
        if temporal_accumulator is not None:
            temporal_accumulator.update(pd.Timestamp(date), day_rank_ic, day_group_returns)


def _load_benchmark_returns(
    panel: pd.DataFrame,
    column: str | None,
) -> pd.Series | None:
    if column is None:
        return None
    if column not in panel.columns:
        raise KeyError(f"Missing benchmark return column: {column}")
    values = pd.to_numeric(panel[column], errors="coerce")
    values.index = pd.to_datetime(panel.index.get_level_values("date"))
    return values


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
    benchmark_return_column: str | None = None,
    benchmark_name: str | None = None,
    regime_window: int = 252,
    holding_period_days: int | None = None,
) -> dict[str, Any]:
    """Build a public snapshot by reading a partitioned factor store incrementally."""
    if group_count < 2:
        raise ValueError("group_count must be at least 2")
    validate_benchmark_source(return_column, benchmark_return_column)
    manifest_file = Path(manifest_path)
    manifest = read_factor_store_manifest(manifest_file)
    selected = _selected_families(manifest, families)
    root = manifest_file.parent
    base_path = root / str(manifest["base_panel"]["path"])
    benchmark_panel = None
    if benchmark_return_column is not None:
        benchmark_panel = ensure_date_ticker_index(
            pd.read_parquet(base_path, columns=[benchmark_return_column])
        )
    temporal_accumulator = TemporalSliceAccumulator(
        [],
        benchmark_returns=(
            _load_benchmark_returns(benchmark_panel, benchmark_return_column)
            if benchmark_panel is not None
            else None
        ),
        regime_window=regime_window,
        benchmark_name=benchmark_name or benchmark_return_column,
    )
    start = pd.Timestamp(date_start) if date_start else None
    end = pd.Timestamp(date_end) if date_end else None

    sums: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    ic_values: dict[str, list[float]] = defaultdict(list)
    rank_ic_values: dict[str, list[float]] = defaultdict(list)
    rank_ic_series: dict[str, list[float]] = defaultdict(list)
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
                temporal_accumulator.add_factors(current_factor_names)
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
                temporal_accumulator=temporal_accumulator,
                rank_ic_series=rank_ic_series,
            )

    if not factor_names:
        raise ValueError("No factor partitions match the requested range")

    temporal = temporal_accumulator.result()
    factor_uncertainty, uncertainty_summary, multiple_testing = _inference_fields(
        rank_ic_series,
        holding_period_days,
    )

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
                "annual_slices": temporal["annual"].get(factor, []),
                "regime_slices": temporal["regime"].get(factor, []),
                "uncertainty": factor_uncertainty[factor],
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
        "config": {
            "group_count": group_count,
            "source": "partitioned_factor_store",
            "holding_period_days": holding_period_days,
            "benchmark_name": benchmark_name or benchmark_return_column,
            "regime_rule": temporal["regime_metadata"]["rule"],
            "regime_window": regime_window,
        },
        "factors": factor_payload,
        "uncertainty": uncertainty_summary,
        "temporal_validation": {
            "status": "partial" if temporal["regime_status"]["status"] != "complete" else "complete",
            "annual_status": "complete",
            "market_regime": temporal["regime_status"],
            "regime_metadata": temporal["regime_metadata"],
        },
        "multiple_testing": multiple_testing,
        "public_limits": [
            "Aggregate evidence only; no ticker-level values or portfolio weights.",
            "Evidence is descriptive research output and is not a return guarantee.",
        ],
    }
    payload["quality"] = build_signal_quality_report(payload)
    result = _json_safe(payload)
    audit_public_snapshot(result)
    return result


def build_factor_evidence_snapshot_from_archive(
    archive_path: str | Path,
    *,
    families: Iterable[str] | None = None,
    date_start: object | None = None,
    date_end: object | None = None,
    return_column: str = "next_period_return",
    data_version: str = "unknown",
    group_count: int = 5,
    code_revision: str | None = None,
    benchmark_return_column: str | None = None,
    benchmark_name: str | None = None,
    regime_window: int = 252,
    holding_period_days: int | None = None,
) -> dict[str, Any]:
    """Build public evidence from an uncompressed tar factor-store archive.

    The archive is accessed through seekable member views. Parquet members are
    read one at a time and the tar file is never extracted or modified.
    """
    if group_count < 2:
        raise ValueError("group_count must be at least 2")
    validate_benchmark_source(return_column, benchmark_return_column)
    archive_file = Path(archive_path)
    manifest, members, prefix = _archive_manifest(archive_file)
    selected = _selected_families(manifest, families)
    start = pd.Timestamp(date_start) if date_start else None
    end = pd.Timestamp(date_end) if date_end else None

    base_relative = str(manifest["base_panel"]["path"]).lstrip("./")
    base_member = members.get(f"{prefix}{base_relative}")
    if base_member is None:
        raise ValueError(f"Archive is missing base panel: {base_relative}")
    base_columns = [return_column]
    if benchmark_return_column and benchmark_return_column not in base_columns:
        base_columns.append(benchmark_return_column)
    base_frame = ensure_date_ticker_index(
        _read_tar_parquet(archive_file, base_member, columns=base_columns)
    )
    temporal_accumulator = TemporalSliceAccumulator(
        [],
        benchmark_returns=_load_benchmark_returns(base_frame, benchmark_return_column),
        regime_window=regime_window,
        benchmark_name=benchmark_name or benchmark_return_column,
    )

    sums: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    ic_values: dict[str, list[float]] = defaultdict(list)
    rank_ic_values: dict[str, list[float]] = defaultdict(list)
    rank_ic_series: dict[str, list[float]] = defaultdict(list)
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
            relative = str(relative_path).lstrip("./")
            factor_member = members.get(f"{prefix}{relative}")
            if factor_member is None:
                raise ValueError(f"Archive is missing factor partition: {relative}")
            factor_frame = ensure_date_ticker_index(_read_tar_parquet(archive_file, factor_member))
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
                temporal_accumulator.add_factors(current_factor_names)
                registered_families.add(family)
            if family == selected[0]:
                observation_count += len(factor_frame)
            first_date = factor_frame.index.get_level_values("date").min()
            last_date = factor_frame.index.get_level_values("date").max()
            base_chunk = base_frame.loc[
                (base_frame.index.get_level_values("date") >= first_date)
                & (base_frame.index.get_level_values("date") <= last_date)
            ]
            _update_chunk(
                factor_frame,
                base_chunk[return_column],
                group_count=group_count,
                sums=sums,
                counts=counts,
                ic_values=ic_values,
                rank_ic_values=rank_ic_values,
                valid_counts=valid_counts,
                total_observations=total_observations,
                dates_seen=dates_seen,
                tickers_seen=tickers_seen,
                temporal_accumulator=temporal_accumulator,
                rank_ic_series=rank_ic_series,
            )

    if not factor_names:
        raise ValueError("No factor partitions match the requested range")

    temporal = temporal_accumulator.result()
    factor_uncertainty, uncertainty_summary, multiple_testing = _inference_fields(
        rank_ic_series,
        holding_period_days,
    )

    def metric(values: np.ndarray) -> dict[str, float | None]:
        mean = float(values.mean()) if len(values) else None
        std = float(values.std(ddof=0)) if len(values) else None
        return {
            "mean": mean,
            "ir": float(mean / std) if mean is not None and std else None,
            "positive_rate": float((values > 0).mean()) if len(values) else None,
        }

    factor_payload: list[dict[str, Any]] = []
    for factor in factor_names:
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
                "ic": metric(np.asarray(ic_values[factor], dtype=float)),
                "rank_ic": metric(np.asarray(rank_ic_values[factor], dtype=float)),
                "annual_slices": temporal["annual"].get(factor, []),
                "regime_slices": temporal["regime"].get(factor, []),
                "uncertainty": factor_uncertainty[factor],
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
        "config": {
            "group_count": group_count,
            "source": "tar_factor_store_archive",
            "holding_period_days": holding_period_days,
            "benchmark_name": benchmark_name or benchmark_return_column,
            "regime_rule": temporal["regime_metadata"]["rule"],
            "regime_window": regime_window,
        },
        "factors": factor_payload,
        "uncertainty": uncertainty_summary,
        "temporal_validation": {
            "status": "partial" if temporal["regime_status"]["status"] != "complete" else "complete",
            "annual_status": "complete",
            "market_regime": temporal["regime_status"],
            "regime_metadata": temporal["regime_metadata"],
        },
        "multiple_testing": multiple_testing,
        "public_limits": [
            "Aggregate evidence only; no ticker-level values or portfolio weights.",
            "Evidence is descriptive research output and is not a return guarantee.",
        ],
    }
    payload["quality"] = build_signal_quality_report(payload)
    result = _json_safe(payload)
    audit_public_snapshot(result)
    return result


def build_signal_quality_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build an aggregate-only quality gate from a public evidence snapshot."""
    factors = list(snapshot.get("factors", []))
    coverage = [
        item["coverage"]["ratio"]
        for item in factors
        if item.get("coverage", {}).get("ratio") is not None
    ]
    rank_ic = [
        item["rank_ic"]["mean"]
        for item in factors
        if item.get("rank_ic", {}).get("mean") is not None
    ]
    positive_rate = [
        item["rank_ic"]["positive_rate"]
        for item in factors
        if item.get("rank_ic", {}).get("positive_rate") is not None
    ]
    low_coverage = sum(value < 0.80 for value in coverage)
    missing_rank_ic = len(factors) - len(rank_ic)
    checks = [
        {
            "name": "factor_count",
            "status": "pass" if factors else "fail",
            "value": len(factors),
            "threshold": ">= 1",
        },
        {
            "name": "coverage",
            "status": "pass" if not low_coverage else "warn",
            "value": low_coverage,
            "threshold": "factors below 80% coverage = 0",
        },
        {
            "name": "rank_ic_availability",
            "status": "pass" if not missing_rank_ic else "warn",
            "value": missing_rank_ic,
            "threshold": "missing RankIC means = 0",
        },
    ]
    status = (
        "fail"
        if any(item["status"] == "fail" for item in checks)
        else ("warn" if any(item["status"] == "warn" for item in checks) else "pass")
    )
    return {
        "schema_version": SIGNAL_QUALITY_SCHEMA_VERSION,
        "status": status,
        "checks": checks,
        "summary": {
            "factor_count": len(factors),
            "coverage_mean": float(np.mean(coverage)) if coverage else None,
            "coverage_min": float(np.min(coverage)) if coverage else None,
            "rank_ic_mean": float(np.mean(rank_ic)) if rank_ic else None,
            "rank_ic_positive_rate_mean": float(np.mean(positive_rate)) if positive_rate else None,
            "low_coverage_factor_count": low_coverage,
            "missing_rank_ic_factor_count": missing_rank_ic,
        },
        "source": {
            "data_version": snapshot.get("data_version"),
            "date_start": snapshot.get("dataset", {}).get("date_start"),
            "date_end": snapshot.get("dataset", {}).get("date_end"),
            "generated_at": snapshot.get("generated_at"),
        },
        "public_limits": [
            "Aggregate diagnostics only; no ticker-level values or portfolio weights.",
            "Quality status is a research-data gate, not a performance or trading guarantee.",
        ],
    }
