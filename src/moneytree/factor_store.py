from __future__ import annotations

import hashlib
import json
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from moneytree._factor_store_manifest import (
    FACTOR_STORE_MANIFEST_VERSION,
    _part_metadata_by_path,
    _require_local_entry_compatible,
    new_factor_store_manifest,
    read_factor_store_manifest,
)
from moneytree._factor_store_validation import (
    FactorStoreValidationError,
    _validate_unique_date_ticker,
    validate_factor_store_keys,
)
from moneytree.data import (
    DEFAULT_PARQUET_COMPRESSION,
    FACTOR_FAMILY_PREFIXES,
    coerce_factor_columns,
    ensure_date_ticker_index,
    factor_columns,
    load_market_data,
    normalize_factor_dtype,
    parquet_write_options,
    save_market_data,
)
from moneytree.factors.external import (
    external_alpha_columns,
    normalize_date_ticker_frame,
    sanitize_manifest_metadata,
)
from moneytree.factors.qlib import build_alpha158_features, build_alpha360_features
from moneytree.metadata import dataframe_schema_hash

LOCAL_FACTOR_FAMILIES = ("alpha158", "alpha360")
EXTERNAL_FACTOR_FAMILIES = ("alpha101", "alpha191")
LOCAL_FACTOR_COUNTS = {"alpha158": 158, "alpha360": 360}


@dataclass(frozen=True)
class _FamilyWriteStats:
    entry: dict[str, Any]
    generated_parts: int
    skipped_parts: int


@dataclass(frozen=True)
class FactorStoreLoadEstimate:
    rows: int
    columns: int
    selected_families: tuple[str, ...]
    required_bytes: int


def _normalize_families(families: Iterable[str] | None) -> tuple[str, ...]:
    if families is None:
        return ()
    normalized: list[str] = []
    for family in families:
        key = str(family).strip().lower().replace("-", "_")
        if not key:
            continue
        if key not in FACTOR_FAMILY_PREFIXES:
            choices = ", ".join(sorted(FACTOR_FAMILY_PREFIXES))
            raise ValueError(f"Unsupported factor family '{family}'. Expected one of: {choices}.")
        normalized.append(key)
    return tuple(dict.fromkeys(normalized))


def _normalize_local_families(families: Iterable[str] | None) -> tuple[str, ...]:
    normalized = _normalize_families(families)
    if not normalized:
        raise ValueError("At least one local factor family is required.")
    unsupported = [family for family in normalized if family not in LOCAL_FACTOR_FAMILIES]
    if unsupported:
        choices = ", ".join(LOCAL_FACTOR_FAMILIES)
        raise ValueError(
            f"Unsupported local factor families: {', '.join(unsupported)}. "
            f"Expected one of: {choices}."
        )
    return normalized


def _families_from_columns(columns: Iterable[object]) -> tuple[str, ...]:
    names = [str(column) for column in columns]
    return tuple(
        family
        for family, prefix in FACTOR_FAMILY_PREFIXES.items()
        if any(column.startswith(prefix) for column in names)
    )


def _family_columns(columns: Iterable[object], family: str) -> list[str]:
    prefix = FACTOR_FAMILY_PREFIXES[family]
    return [str(column) for column in columns if str(column).startswith(prefix)]


def _expected_external_family_columns(family: str) -> list[str]:
    if family not in EXTERNAL_FACTOR_FAMILIES:
        raise ValueError(f"Unsupported external factor family: {family}")
    return external_alpha_columns(family)


def _relative_path(base_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def _resolve_store_path(root: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else root / path


def _format_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m{int(remainder):02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h{int(minutes):02d}m"


def _progress_bar(current: int, total: int, *, width: int = 20) -> str:
    if total <= 0:
        return f"[{'-' * width}]"
    filled = min(width, max(0, round(width * int(current) / int(total))))
    return f"[{'#' * filled}{'-' * (width - filled)}]"


def _date_value(value: object) -> str:
    return str(pd.Timestamp(value).date())


def _frame_content_hash(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update(dataframe_schema_hash(frame).encode("utf-8"))
    hashed = pd.util.hash_pandas_object(frame, index=True).to_numpy(dtype="uint64", copy=False)
    digest.update(hashed.tobytes())
    return digest.hexdigest()


def _read_parquet_index(path: Path) -> pd.Index:
    frame = pd.read_parquet(path, columns=[])
    return ensure_date_ticker_index(frame).index


def _local_factor_input_columns(frame: pd.DataFrame, family: str, *, adjusted: bool) -> list[str]:
    price_fields = ("open", "high", "low", "close", "vwap")
    columns: list[str] = []
    for field in price_fields:
        adjusted_name = f"{field}_adj"
        if adjusted and adjusted_name in frame.columns:
            columns.append(adjusted_name)
        elif field in frame.columns:
            columns.append(field)
    if "volume" in frame.columns:
        columns.append("volume")
    if family == "alpha158" and "amount" in frame.columns:
        columns.append("amount")
    return list(dict.fromkeys(columns))


def _local_factor_input_columns_from_names(
    column_names: Iterable[str],
    family: str,
    *,
    adjusted: bool,
) -> list[str]:
    available = set(str(column) for column in column_names)
    price_fields = ("open", "high", "low", "close", "vwap")
    columns: list[str] = []
    for field in price_fields:
        adjusted_name = f"{field}_adj"
        if adjusted and adjusted_name in available:
            columns.append(adjusted_name)
        elif field in available:
            columns.append(field)
    if "volume" in available:
        columns.append("volume")
    if family == "alpha158" and "amount" in available:
        columns.append("amount")
    return list(dict.fromkeys(columns))



def _date_range_overlaps(
    *,
    start_date: object | None,
    end_date: object | None,
    date_start: object | None,
    date_end: object | None,
) -> bool:
    if start_date is None or end_date is None:
        return True
    part_start = pd.Timestamp(start_date)
    part_end = pd.Timestamp(end_date)
    requested_start = pd.Timestamp(date_start) if date_start else None
    requested_end = pd.Timestamp(date_end) if date_end else None
    if requested_start is not None and part_end < requested_start:
        return False
    if requested_end is not None and part_start > requested_end:
        return False
    return True


def _entry_paths_for_date_range(
    entry: dict[str, Any],
    *,
    date_start: object | None,
    date_end: object | None,
) -> list[str]:
    paths = [str(path) for path in entry.get("paths", [])]
    if not paths or (not date_start and not date_end):
        return paths
    parts = _part_metadata_by_path(entry)
    if not parts:
        return paths
    return [
        path
        for path in paths
        if _date_range_overlaps(
            start_date=parts.get(path, {}).get("start_date"),
            end_date=parts.get(path, {}).get("end_date"),
            date_start=date_start,
            date_end=date_end,
        )
    ]


def _read_factor_entry(
    root: Path,
    entry: dict[str, Any],
    *,
    date_start: object | None = None,
    date_end: object | None = None,
) -> pd.DataFrame:
    if "paths" in entry:
        frames = [
            load_market_data(
                _resolve_store_path(root, path),
                date_start=date_start,
                date_end=date_end,
            )
            for path in _entry_paths_for_date_range(
                entry,
                date_start=date_start,
                date_end=date_end,
            )
        ]
        if not frames:
            empty_index = pd.MultiIndex.from_arrays([[], []], names=["date", "ticker"])
            return pd.DataFrame(index=empty_index)
        return ensure_date_ticker_index(pd.concat(frames, axis=0)).sort_index()
    return load_market_data(
        _resolve_store_path(root, str(entry["path"])),
        date_start=date_start,
        date_end=date_end,
    )


def _date_chunks(dates: pd.Index, chunk_trade_dates: int) -> list[pd.Index]:
    chunk_size = max(1, int(chunk_trade_dates))
    return [dates[start : start + chunk_size] for start in range(0, len(dates), chunk_size)]


def _family_overlap(family: str) -> int:
    if family == "alpha158":
        return 60
    if family == "alpha360":
        return 59
    raise ValueError(f"Unsupported local factor family: {family}")


def _build_local_family_features(
    frame: pd.DataFrame,
    family: str,
    *,
    adjusted: bool,
    dtype: str,
) -> pd.DataFrame:
    if family == "alpha158":
        return build_alpha158_features(frame, adjusted=adjusted, dtype=dtype)
    if family == "alpha360":
        return build_alpha360_features(frame, adjusted=adjusted, dtype=dtype)
    raise ValueError(f"Unsupported local factor family: {family}")


def _write_partitioned_local_family(
    base_frame: pd.DataFrame,
    root: Path,
    family: str,
    *,
    existing_entry: dict[str, Any] | None,
    existing_base_frame: pd.DataFrame | None,
    overwrite: bool,
    adjusted: bool,
    factor_dtype: str,
    chunk_trade_dates: int,
    compression: str,
    compression_level: int | None,
    row_group_size: int | None,
    show_progress: bool,
) -> _FamilyWriteStats:
    dates = pd.Index(base_frame.index.get_level_values("date").unique()).sort_values()
    chunks = _date_chunks(dates, chunk_trade_dates)
    overlap = _family_overlap(family)
    family_dir = root / "factors" / family
    family_dir.mkdir(parents=True, exist_ok=True)

    date_index = base_frame.index.get_level_values("date")
    existing_date_index = (
        existing_base_frame.index.get_level_values("date")
        if existing_base_frame is not None
        else None
    )
    input_columns = _local_factor_input_columns(base_frame, family, adjusted=adjusted)
    existing_parts = _part_metadata_by_path(existing_entry)
    started_at = time.perf_counter()
    paths: list[str] = []
    parts: list[dict[str, Any]] = []
    rows = 0
    columns = int(
        (existing_entry or {}).get("columns")
        or LOCAL_FACTOR_COUNTS.get(family, 0)
    )
    generated_parts = 0
    skipped_parts = 0

    if show_progress and len(chunks) > 0:
        print(
            (
                f"[factor-store:{family}] start parts={len(chunks)} "
                f"rows={len(base_frame)} start={_date_value(dates[0])} "
                f"end={_date_value(dates[-1])} chunk_trade_dates={int(chunk_trade_dates)}"
            ),
            file=sys.stderr,
            flush=True,
        )

    for idx, target_dates in enumerate(chunks, start=1):
        part_started_at = time.perf_counter()
        target_start = (idx - 1) * max(1, int(chunk_trade_dates))
        calc_start = max(0, target_start - overlap)
        calc_dates = dates[calc_start : target_start + len(target_dates)]
        calc_panel = base_frame.loc[date_index.isin(calc_dates)]
        target_frame = base_frame.loc[date_index.isin(target_dates)].sort_index()
        part_path = family_dir / f"part-{idx:04d}.parquet"
        relative_part_path = _relative_path(root, part_path)
        part_input_hash = _frame_content_hash(calc_panel.loc[:, input_columns])
        existing_part = existing_parts.get(relative_part_path)
        can_reuse = False

        if existing_entry is not None and not overwrite and part_path.exists():
            try:
                existing_index = _read_parquet_index(part_path)
                can_reuse = existing_index.equals(target_frame.index)
                if can_reuse and existing_part and existing_part.get("input_hash"):
                    can_reuse = str(existing_part["input_hash"]) == part_input_hash
                elif can_reuse and existing_base_frame is not None and existing_date_index is not None:
                    existing_calc_panel = existing_base_frame.loc[existing_date_index.isin(calc_dates)]
                    can_reuse = (
                        existing_calc_panel.index.equals(calc_panel.index)
                        and _frame_content_hash(existing_calc_panel.loc[:, input_columns])
                        == part_input_hash
                    )
                else:
                    can_reuse = False
            except Exception:
                can_reuse = False

        if can_reuse:
            skipped_parts += 1
            status = "skipped"
        else:
            features = _build_local_family_features(
                calc_panel,
                family,
                adjusted=adjusted,
                dtype=factor_dtype,
            )
            target_mask = features.index.get_level_values("date").isin(target_dates)
            target_features = features.loc[target_mask].sort_index()
            save_market_data(
                target_features,
                part_path,
                compression=compression,
                compression_level=compression_level,
                row_group_size=row_group_size,
            )
            columns = int(len(target_features.columns))
            generated_parts += 1
            status = "generated"

        part_rows = int(len(target_frame))
        paths.append(relative_part_path)
        rows += part_rows
        parts.append(
            {
                "path": relative_part_path,
                "start_date": _date_value(target_dates[0]),
                "end_date": _date_value(target_dates[-1]),
                "rows": part_rows,
                "columns": columns,
                "input_hash": part_input_hash,
            }
        )

        if show_progress:
            elapsed = time.perf_counter() - started_at
            remaining = (elapsed / idx) * (len(chunks) - idx) if idx else 0.0
            print(
                (
                    f"[factor-store:{family}] part={idx}/{len(chunks)} "
                    f"progress={_progress_bar(idx, len(chunks))} "
                    f"status={status} rows={rows} start={_date_value(target_dates[0])} "
                    f"end={_date_value(target_dates[-1])} "
                    f"part_elapsed={_format_duration(time.perf_counter() - part_started_at)} "
                    f"elapsed={_format_duration(elapsed)} eta={_format_duration(remaining)}"
                ),
                file=sys.stderr,
                flush=True,
            )

    if show_progress:
        print(
            (
                f"[factor-store:{family}] done parts={len(chunks)} generated={generated_parts} "
                f"skipped={skipped_parts} rows={rows} elapsed={_format_duration(time.perf_counter() - started_at)}"
            ),
            file=sys.stderr,
            flush=True,
        )

    entry = {
        "paths": paths,
        "parts": parts,
        "partitioned": True,
        "prefix": FACTOR_FAMILY_PREFIXES[family],
        "rows": rows,
        "columns": columns,
        "chunk_trade_dates": int(chunk_trade_dates),
        "factor_dtype": factor_dtype,
        "adjusted": bool(adjusted),
        "compression": compression,
        "compression_level": compression_level,
        "row_group_size": row_group_size,
    }
    return _FamilyWriteStats(
        entry=entry,
        generated_parts=generated_parts,
        skipped_parts=skipped_parts,
    )


def _parquet_schema_columns(path: Path) -> list[str]:
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - pyarrow is a core dependency
        raise RuntimeError("Parquet factor-store streaming requires pyarrow.") from exc
    return [str(name) for name in pq.read_schema(path).names]


def _parquet_trade_dates(path: Path, *, batch_size: int = 250_000) -> pd.Index:
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - pyarrow is a core dependency
        raise RuntimeError("Parquet factor-store streaming requires pyarrow.") from exc

    if "date" not in _parquet_schema_columns(path):
        raise FactorStoreValidationError("Input parquet must contain a date column or date index.")

    seen: dict[str, object] = {}
    parquet_file = pq.ParquetFile(path)
    for batch in parquet_file.iter_batches(columns=["date"], batch_size=int(batch_size)):
        values = batch.column(batch.schema.get_field_index("date")).to_pandas()
        for value in pd.unique(values.dropna()):
            seen.setdefault(str(value), value)

    dates = pd.Index(seen.values())
    if dates.empty:
        raise FactorStoreValidationError("Input parquet has no non-null trade dates.")
    return dates.sort_values()


def _parquet_num_rows(path: Path) -> int:
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - pyarrow is a core dependency
        raise RuntimeError("Parquet factor-store streaming requires pyarrow.") from exc
    return int(pq.ParquetFile(path).metadata.num_rows)


def _parquet_writer_options(
    *,
    compression: str,
    compression_level: int | None,
    row_group_size: int | None,
) -> tuple[dict[str, object], int | None]:
    options = parquet_write_options(
        compression=compression,
        compression_level=compression_level,
        row_group_size=row_group_size,
    )
    normalized_row_group_size = options.pop("row_group_size", None)
    return options, (
        int(normalized_row_group_size) if normalized_row_group_size is not None else None
    )


def _stream_copy_base_parquet(
    input_path: Path,
    output_path: Path,
    *,
    storage_columns: list[str],
    data_columns: list[str],
    compression: str,
    compression_level: int | None,
    row_group_size: int | None,
    batch_size: int = 250_000,
) -> dict[str, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - pyarrow is a core dependency
        raise RuntimeError("Parquet factor-store streaming requires pyarrow.") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer_options, normalized_row_group_size = _parquet_writer_options(
        compression=compression,
        compression_level=compression_level,
        row_group_size=row_group_size,
    )
    parquet_file = pq.ParquetFile(input_path)
    writer: pq.ParquetWriter | None = None
    schema_hash: str | None = None
    content_digest = hashlib.sha256()
    rows = 0
    try:
        for batch in parquet_file.iter_batches(
            columns=storage_columns,
            batch_size=int(batch_size),
        ):
            table = pa.Table.from_batches([batch])
            if writer is None:
                writer = pq.ParquetWriter(output_path, table.schema, **writer_options)

            frame = table.to_pandas()
            indexed = ensure_date_ticker_index(frame)
            base_frame = indexed.loc[:, data_columns]
            if schema_hash is None:
                schema_hash = dataframe_schema_hash(base_frame)
                content_digest.update(schema_hash.encode("utf-8"))
            row_hashes = pd.util.hash_pandas_object(
                base_frame,
                index=True,
            ).to_numpy(dtype="uint64", copy=False)
            content_digest.update(row_hashes.tobytes())
            rows += int(len(base_frame))

            writer.write_table(table, row_group_size=normalized_row_group_size)
    finally:
        if writer is not None:
            writer.close()

    if schema_hash is None:
        empty_index = pd.MultiIndex.from_arrays([[], []], names=["date", "ticker"])
        schema_hash = dataframe_schema_hash(pd.DataFrame(columns=data_columns, index=empty_index))
        content_digest.update(schema_hash.encode("utf-8"))

    return {
        "rows": rows,
        "columns": int(len(data_columns)),
        "schema_hash": schema_hash,
        "content_hash": content_digest.hexdigest(),
    }


def _read_parquet_panel_window(
    input_path: Path,
    dates: pd.Index,
    *,
    data_columns: list[str],
) -> pd.DataFrame:
    schema_columns = set(_parquet_schema_columns(input_path))
    columns = [column for column in data_columns if column in schema_columns]
    for key in ("date", "ticker"):
        if key in schema_columns and key not in columns:
            columns.append(key)
    frame = pd.read_parquet(
        input_path,
        columns=columns,
        filters=[("date", "in", list(dates))],
    )
    return ensure_date_ticker_index(frame)


def _write_partitioned_local_family_from_parquet(
    input_path: Path,
    root: Path,
    family: str,
    *,
    dates: pd.Index,
    schema_columns: list[str],
    existing_entry: dict[str, Any] | None,
    manifest: dict[str, Any],
    overwrite: bool,
    adjusted: bool,
    factor_dtype: str,
    chunk_trade_dates: int,
    compression: str,
    compression_level: int | None,
    row_group_size: int | None,
    show_progress: bool,
) -> _FamilyWriteStats:
    chunks = _date_chunks(dates, chunk_trade_dates)
    overlap = _family_overlap(family)
    family_dir = root / "factors" / family
    family_dir.mkdir(parents=True, exist_ok=True)
    input_columns = _local_factor_input_columns_from_names(
        schema_columns,
        family,
        adjusted=adjusted,
    )
    existing_parts = _part_metadata_by_path(existing_entry)
    started_at = time.perf_counter()
    paths: list[str] = []
    parts: list[dict[str, Any]] = []
    rows = 0
    columns = int(
        (existing_entry or {}).get("columns")
        or LOCAL_FACTOR_COUNTS.get(family, 0)
    )
    generated_parts = 0
    skipped_parts = 0

    if show_progress and len(chunks) > 0:
        print(
            (
                f"[factor-store:{family}] start parts={len(chunks)} "
                f"input=streaming rows={_parquet_num_rows(input_path)} "
                f"start={_date_value(dates[0])} end={_date_value(dates[-1])} "
                f"chunk_trade_dates={int(chunk_trade_dates)}"
            ),
            file=sys.stderr,
            flush=True,
        )

    for idx, target_dates in enumerate(chunks, start=1):
        part_started_at = time.perf_counter()
        target_start = (idx - 1) * max(1, int(chunk_trade_dates))
        calc_start = max(0, target_start - overlap)
        calc_dates = dates[calc_start : target_start + len(target_dates)]
        calc_panel = _read_parquet_panel_window(
            input_path,
            calc_dates,
            data_columns=input_columns,
        )
        date_index = calc_panel.index.get_level_values("date")
        target_frame = calc_panel.loc[date_index.isin(target_dates)].sort_index()
        part_path = family_dir / f"part-{idx:04d}.parquet"
        relative_part_path = _relative_path(root, part_path)
        part_input_hash = _frame_content_hash(calc_panel.loc[:, input_columns])
        existing_part = existing_parts.get(relative_part_path)
        can_reuse = False

        if existing_entry is not None and not overwrite and part_path.exists():
            try:
                existing_index = _read_parquet_index(part_path)
                can_reuse = existing_index.equals(target_frame.index)
                if can_reuse and existing_part and existing_part.get("input_hash"):
                    can_reuse = str(existing_part["input_hash"]) == part_input_hash
                else:
                    can_reuse = False
            except Exception:
                can_reuse = False

        if can_reuse:
            skipped_parts += 1
            status = "skipped"
        else:
            features = _build_local_family_features(
                calc_panel,
                family,
                adjusted=adjusted,
                dtype=factor_dtype,
            )
            target_mask = features.index.get_level_values("date").isin(target_dates)
            target_features = features.loc[target_mask].sort_index()
            save_market_data(
                target_features,
                part_path,
                compression=compression,
                compression_level=compression_level,
                row_group_size=row_group_size,
            )
            columns = int(len(target_features.columns))
            generated_parts += 1
            status = "generated"

        part_rows = int(len(target_frame))
        paths.append(relative_part_path)
        rows += part_rows
        parts.append(
            {
                "path": relative_part_path,
                "start_date": _date_value(target_dates[0]),
                "end_date": _date_value(target_dates[-1]),
                "rows": part_rows,
                "columns": columns,
                "input_hash": part_input_hash,
            }
        )

        if show_progress:
            elapsed = time.perf_counter() - started_at
            remaining = (elapsed / idx) * (len(chunks) - idx) if idx else 0.0
            print(
                (
                    f"[factor-store:{family}] part={idx}/{len(chunks)} "
                    f"progress={_progress_bar(idx, len(chunks))} "
                    f"status={status} rows={rows} start={_date_value(target_dates[0])} "
                    f"end={_date_value(target_dates[-1])} "
                    f"part_elapsed={_format_duration(time.perf_counter() - part_started_at)} "
                    f"elapsed={_format_duration(elapsed)} eta={_format_duration(remaining)}"
                ),
                file=sys.stderr,
                flush=True,
            )

    if show_progress:
        print(
            (
                f"[factor-store:{family}] done parts={len(chunks)} generated={generated_parts} "
                f"skipped={skipped_parts} rows={rows} elapsed={_format_duration(time.perf_counter() - started_at)}"
            ),
            file=sys.stderr,
            flush=True,
        )

    entry = {
        "paths": paths,
        "parts": parts,
        "partitioned": True,
        "prefix": FACTOR_FAMILY_PREFIXES[family],
        "rows": rows,
        "columns": columns,
        "chunk_trade_dates": int(chunk_trade_dates),
        "factor_dtype": factor_dtype,
        "adjusted": bool(adjusted),
        "compression": compression,
        "compression_level": compression_level,
        "row_group_size": row_group_size,
    }
    return _FamilyWriteStats(
        entry=entry,
        generated_parts=generated_parts,
        skipped_parts=skipped_parts,
    )


def write_partitioned_factor_family(
    factor_frame: pd.DataFrame,
    root: str | Path,
    family: str,
    *,
    chunk_trade_dates: int = 60,
    compression: str = DEFAULT_PARQUET_COMPRESSION,
    compression_level: int | None = None,
    row_group_size: int | None = None,
    show_progress: bool = False,
    source: str | None = None,
) -> dict[str, Any]:
    """Write an already-computed factor family frame into date partitions."""
    family_key = _normalize_families([family])[0]
    indexed = _validate_unique_date_ticker(factor_frame, source_name=f"{family_key} factors")
    root_path = Path(root)
    dates = pd.Index(indexed.index.get_level_values("date").unique()).sort_values()
    chunks = _date_chunks(dates, chunk_trade_dates)
    family_dir = root_path / "factors" / family_key
    family_dir.mkdir(parents=True, exist_ok=True)

    date_index = indexed.index.get_level_values("date")
    paths: list[str] = []
    rows = 0
    columns = int(len(indexed.columns))
    for idx, target_dates in enumerate(chunks, start=1):
        target_frame = indexed.loc[date_index.isin(target_dates)].sort_index()
        part_path = family_dir / f"part-{idx:04d}.parquet"
        save_market_data(
            target_frame,
            part_path,
            compression=compression,
            compression_level=compression_level,
            row_group_size=row_group_size,
        )
        paths.append(_relative_path(root_path, part_path))
        rows += int(len(target_frame))
        if show_progress:
            start_value = pd.Timestamp(target_dates[0]).date()
            end_value = pd.Timestamp(target_dates[-1]).date()
            print(
                (
                    f"[factor-store:{family_key}] part={idx}/{len(chunks)} "
                    f"rows={rows} start={start_value} end={end_value}"
                ),
                file=sys.stderr,
                flush=True,
            )

    entry: dict[str, Any] = {
        "paths": paths,
        "partitioned": True,
        "prefix": FACTOR_FAMILY_PREFIXES[family_key],
        "rows": rows,
        "columns": columns,
        "chunk_trade_dates": int(chunk_trade_dates),
    }
    if source:
        entry["source"] = source
    return entry


def write_external_factor_store_partitioned(
    base_panel: pd.DataFrame,
    output_dir: str | Path,
    *,
    families: Iterable[str],
    generate_family_part: Callable[[str, pd.Index, int, int], pd.DataFrame],
    factor_dtype: str = "float32",
    chunk_trade_dates: int = 60,
    metadata: dict[str, Any] | None = None,
    compression: str = DEFAULT_PARQUET_COMPRESSION,
    compression_level: int | None = None,
    row_group_size: int | None = None,
    overwrite: bool = False,
    show_progress: bool = False,
) -> dict[str, Any]:
    """Write external Alpha101/191 families while generating one date partition at a time."""
    requested_families = _normalize_families(families)
    unsupported = [family for family in requested_families if family not in EXTERNAL_FACTOR_FAMILIES]
    if unsupported:
        choices = ", ".join(EXTERNAL_FACTOR_FAMILIES)
        raise ValueError(
            f"Unsupported external factor families: {', '.join(unsupported)}. "
            f"Expected one of: {choices}."
        )
    if not requested_families:
        raise ValueError("At least one external factor family is required.")

    dtype = normalize_factor_dtype(factor_dtype)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    indexed_base = _validate_unique_date_ticker(base_panel, source_name="base panel")
    base_columns = [
        column for column in indexed_base.columns if column not in factor_columns(indexed_base.columns)
    ]
    base_frame = indexed_base.loc[:, base_columns]

    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = read_factor_store_manifest(manifest_path)
        existing_base_path = _resolve_store_path(root, manifest["base_panel"]["path"])
        if existing_base_path.exists():
            existing_base = _validate_unique_date_ticker(
                load_market_data(existing_base_path),
                source_name="base panel",
            )
            if not existing_base.index.equals(base_frame.index):
                raise FactorStoreValidationError(
                    "Existing factor store base panel index does not match the input panel."
                )
    else:
        manifest = new_factor_store_manifest()

    base_path = root / "base.parquet"
    save_market_data(
        base_frame,
        base_path,
        compression=compression,
        compression_level=compression_level,
        row_group_size=row_group_size,
    )

    dates = pd.Index(base_frame.index.get_level_values("date").unique()).sort_values()
    chunks = _date_chunks(dates, chunk_trade_dates)
    date_index = base_frame.index.get_level_values("date")
    factor_entries = dict(manifest.get("factor_families", {}))
    generated: list[str] = []
    skipped: list[str] = []
    parts_generated: dict[str, int] = {}

    for family in requested_families:
        if family in factor_entries and not overwrite:
            skipped.append(family)
            parts_generated[family] = 0
            continue

        expected_columns = _expected_external_family_columns(family)
        family_dir = root / "factors" / family
        family_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        parts: list[dict[str, Any]] = []
        rows = 0
        started_at = time.perf_counter()

        if show_progress and len(chunks) > 0:
            print(
                (
                    f"[factor-store:{family}] start parts={len(chunks)} rows={len(base_frame)} "
                    f"start={_date_value(dates[0])} end={_date_value(dates[-1])} "
                    f"chunk_trade_dates={int(chunk_trade_dates)}"
                ),
                file=sys.stderr,
                flush=True,
            )

        for idx, target_dates in enumerate(chunks, start=1):
            part_started_at = time.perf_counter()
            target_frame = base_frame.loc[date_index.isin(target_dates)].sort_index()
            generated_part = generate_family_part(family, target_dates, idx, len(chunks))
            indexed_factors = normalize_date_ticker_frame(
                generated_part,
                source_name=f"{family} generated part {idx}",
            )
            missing = [column for column in expected_columns if column not in indexed_factors.columns]
            if missing:
                raise FactorStoreValidationError(
                    f"{family} factors are missing expected columns: {missing}."
                )

            factor_part = coerce_factor_columns(
                indexed_factors.loc[:, expected_columns],
                dtype,
            ).sort_index()
            if not factor_part.index.equals(target_frame.index):
                missing_keys = target_frame.index.difference(factor_part.index)
                extra_keys = factor_part.index.difference(target_frame.index)
                raise FactorStoreValidationError(
                    f"{family} generated part {idx} is not aligned with the target "
                    f"date/ticker keys (missing={len(missing_keys)}, extra={len(extra_keys)})."
                )

            part_path = family_dir / f"part-{idx:04d}.parquet"
            save_market_data(
                factor_part,
                part_path,
                compression=compression,
                compression_level=compression_level,
                row_group_size=row_group_size,
            )
            relative_part_path = _relative_path(root, part_path)
            part_rows = int(len(factor_part))
            rows += part_rows
            paths.append(relative_part_path)
            parts.append(
                {
                    "path": relative_part_path,
                    "start_date": _date_value(target_dates[0]),
                    "end_date": _date_value(target_dates[-1]),
                    "rows": part_rows,
                    "columns": len(expected_columns),
                }
            )

            if show_progress:
                elapsed = time.perf_counter() - started_at
                remaining = (elapsed / idx) * (len(chunks) - idx) if idx else 0.0
                print(
                    (
                        f"[factor-store:{family}] part={idx}/{len(chunks)} "
                        f"progress={_progress_bar(idx, len(chunks))} rows={rows} "
                        f"start={_date_value(target_dates[0])} "
                        f"end={_date_value(target_dates[-1])} "
                        f"part_elapsed={_format_duration(time.perf_counter() - part_started_at)} "
                        f"elapsed={_format_duration(elapsed)} eta={_format_duration(remaining)}"
                    ),
                    file=sys.stderr,
                    flush=True,
                )

        factor_entries[family] = {
            "paths": paths,
            "parts": parts,
            "partitioned": True,
            "prefix": FACTOR_FAMILY_PREFIXES[family],
            "rows": rows,
            "columns": len(expected_columns),
            "chunk_trade_dates": int(chunk_trade_dates),
            "factor_dtype": dtype,
            "compression": compression,
            "compression_level": compression_level,
            "row_group_size": row_group_size,
            "source": "dolphindb",
        }
        generated.append(family)
        parts_generated[family] = len(chunks)

        if show_progress:
            print(
                (
                    f"[factor-store:{family}] done parts={len(chunks)} rows={rows} "
                    f"elapsed={_format_duration(time.perf_counter() - started_at)}"
                ),
                file=sys.stderr,
                flush=True,
            )

    manifest.update(
        {
            "manifest_schema_version": FACTOR_STORE_MANIFEST_VERSION,
            "kind": "moneytree_factor_store",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_panel": {
                "path": _relative_path(root, base_path),
                "rows": int(len(base_frame)),
                "columns": int(len(base_frame.columns)),
                "schema_hash": dataframe_schema_hash(base_frame),
            },
            "factor_families": factor_entries,
            "factor_dtype": dtype,
            "compression": compression,
            "compression_level": compression_level,
            "row_group_size": row_group_size,
            "key_validation": {
                "date_ticker_unique": True,
                "aligned": True,
            },
            "external_generation": sanitize_manifest_metadata(
                {
                    "families_requested": list(requested_families),
                    "families_generated": generated,
                    "families_skipped": skipped,
                    "parts_generated": parts_generated,
                    "source": "dolphindb",
                    "streamed": True,
                    "chunk_trade_dates": int(chunk_trade_dates),
                    "compression": compression,
                    "compression_level": compression_level,
                    "row_group_size": row_group_size,
                    **dict(metadata or {}),
                }
            ),
            "metadata": sanitize_manifest_metadata(
                {**dict(manifest.get("metadata", {})), **dict(metadata or {})}
            ),
        }
    )
    sanitized_manifest = sanitize_manifest_metadata(manifest)
    manifest_path.write_text(json.dumps(sanitized_manifest, indent=2), encoding="utf-8")
    return sanitized_manifest


def write_external_factor_store_partitioned_from_parquet(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    families: Iterable[str],
    generate_family_part: Callable[
        [str, pd.DataFrame, pd.Index, pd.Index, int, int],
        pd.DataFrame,
    ],
    factor_dtype: str = "float32",
    chunk_trade_dates: int = 60,
    warmup_trade_dates: int = 260,
    metadata: dict[str, Any] | None = None,
    compression: str = DEFAULT_PARQUET_COMPRESSION,
    compression_level: int | None = None,
    row_group_size: int | None = None,
    overwrite: bool = False,
    show_progress: bool = False,
) -> dict[str, Any]:
    """Write external Alpha101/191 families from a parquet panel one window at a time."""
    requested_families = _normalize_families(families)
    unsupported = [family for family in requested_families if family not in EXTERNAL_FACTOR_FAMILIES]
    if unsupported:
        choices = ", ".join(EXTERNAL_FACTOR_FAMILIES)
        raise ValueError(
            f"Unsupported external factor families: {', '.join(unsupported)}. "
            f"Expected one of: {choices}."
        )
    if not requested_families:
        raise ValueError("At least one external factor family is required.")

    dtype = normalize_factor_dtype(factor_dtype)
    source_path = Path(input_path)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    schema_columns = _parquet_schema_columns(source_path)
    if not {"date", "ticker"}.issubset(schema_columns):
        raise FactorStoreValidationError("Input parquet must contain date/ticker columns or index.")

    base_data_columns = [
        column
        for column in schema_columns
        if column not in {"date", "ticker"} and column not in factor_columns(schema_columns)
    ]
    base_storage_columns = [*base_data_columns, "date", "ticker"]
    dates = _parquet_trade_dates(source_path)

    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = read_factor_store_manifest(manifest_path)
    else:
        manifest = new_factor_store_manifest()

    factor_entries = dict(manifest.get("factor_families", {}))
    non_requested_existing = [
        family
        for family in factor_entries
        if family not in requested_families
    ]

    base_path = root / "base.parquet"
    base_tmp_path = base_path.with_suffix(base_path.suffix + ".tmp")
    base_summary = _stream_copy_base_parquet(
        source_path,
        base_tmp_path,
        storage_columns=base_storage_columns,
        data_columns=base_data_columns,
        compression=compression,
        compression_level=compression_level,
        row_group_size=row_group_size,
    )

    existing_base = dict(manifest.get("base_panel", {}))
    existing_hash = existing_base.get("content_hash")
    if (
        non_requested_existing
        and existing_hash is not None
        and str(existing_hash) != str(base_summary["content_hash"])
    ):
        base_tmp_path.unlink(missing_ok=True)
        raise FactorStoreValidationError(
            "Existing factor store base panel does not match the input panel. "
            "Request existing families so they can be incrementally updated, or use a new "
            f"output directory. Stale families: {', '.join(non_requested_existing)}."
        )
    base_tmp_path.replace(base_path)

    chunks = _date_chunks(dates, chunk_trade_dates)
    generated: list[str] = []
    skipped: list[str] = []
    parts_generated: dict[str, int] = {}
    parts_skipped: dict[str, int] = {}
    warmup = max(0, int(warmup_trade_dates))

    for family in requested_families:
        existing_entry = factor_entries.get(family)
        if existing_entry is not None and not overwrite:
            skipped.append(family)
            parts_generated[family] = 0
            parts_skipped[family] = len(existing_entry.get("parts", []))
            continue

        expected_columns = _expected_external_family_columns(family)
        family_dir = root / "factors" / family
        family_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        parts: list[dict[str, Any]] = []
        rows = 0
        started_at = time.perf_counter()

        if show_progress and len(chunks) > 0:
            print(
                (
                    f"[factor-store:{family}] start parts={len(chunks)} input=parquet_streaming "
                    f"rows={base_summary['rows']} start={_date_value(dates[0])} "
                    f"end={_date_value(dates[-1])} chunk_trade_dates={int(chunk_trade_dates)} "
                    f"warmup_trade_dates={warmup}"
                ),
                file=sys.stderr,
                flush=True,
            )

        for idx, target_dates in enumerate(chunks, start=1):
            part_started_at = time.perf_counter()
            target_start = (idx - 1) * max(1, int(chunk_trade_dates))
            calc_start = max(0, target_start - warmup)
            calc_dates = dates[calc_start : target_start + len(target_dates)]
            calc_panel = _read_parquet_panel_window(
                source_path,
                calc_dates,
                data_columns=base_data_columns,
            )
            date_index = calc_panel.index.get_level_values("date")
            target_frame = calc_panel.loc[date_index.isin(target_dates)].sort_index()
            generated_part = generate_family_part(
                family,
                calc_panel,
                target_dates,
                calc_dates,
                idx,
                len(chunks),
            )
            indexed_factors = normalize_date_ticker_frame(
                generated_part,
                source_name=f"{family} generated part {idx}",
            )
            missing = [column for column in expected_columns if column not in indexed_factors.columns]
            if missing:
                raise FactorStoreValidationError(
                    f"{family} factors are missing expected columns: {missing}."
                )

            factor_part = coerce_factor_columns(
                indexed_factors.loc[:, expected_columns],
                dtype,
            ).sort_index()
            if not factor_part.index.equals(target_frame.index):
                missing_keys = target_frame.index.difference(factor_part.index)
                extra_keys = factor_part.index.difference(target_frame.index)
                raise FactorStoreValidationError(
                    f"{family} generated part {idx} is not aligned with the target "
                    f"date/ticker keys (missing={len(missing_keys)}, extra={len(extra_keys)})."
                )

            part_path = family_dir / f"part-{idx:04d}.parquet"
            save_market_data(
                factor_part,
                part_path,
                compression=compression,
                compression_level=compression_level,
                row_group_size=row_group_size,
            )
            relative_part_path = _relative_path(root, part_path)
            part_rows = int(len(factor_part))
            rows += part_rows
            paths.append(relative_part_path)
            parts.append(
                {
                    "path": relative_part_path,
                    "start_date": _date_value(target_dates[0]),
                    "end_date": _date_value(target_dates[-1]),
                    "rows": part_rows,
                    "columns": len(expected_columns),
                }
            )

            if show_progress:
                elapsed = time.perf_counter() - started_at
                remaining = (elapsed / idx) * (len(chunks) - idx) if idx else 0.0
                print(
                    (
                        f"[factor-store:{family}] part={idx}/{len(chunks)} "
                        f"progress={_progress_bar(idx, len(chunks))} rows={rows} "
                        f"start={_date_value(target_dates[0])} "
                        f"end={_date_value(target_dates[-1])} "
                        f"part_elapsed={_format_duration(time.perf_counter() - part_started_at)} "
                        f"elapsed={_format_duration(elapsed)} eta={_format_duration(remaining)}"
                    ),
                    file=sys.stderr,
                    flush=True,
                )

        factor_entries[family] = {
            "paths": paths,
            "parts": parts,
            "partitioned": True,
            "prefix": FACTOR_FAMILY_PREFIXES[family],
            "rows": rows,
            "columns": len(expected_columns),
            "chunk_trade_dates": int(chunk_trade_dates),
            "factor_dtype": dtype,
            "compression": compression,
            "compression_level": compression_level,
            "row_group_size": row_group_size,
            "source": "dolphindb",
        }
        generated.append(family)
        parts_generated[family] = len(chunks)
        parts_skipped[family] = 0

        if show_progress:
            print(
                (
                    f"[factor-store:{family}] done parts={len(chunks)} rows={rows} "
                    f"elapsed={_format_duration(time.perf_counter() - started_at)}"
                ),
                file=sys.stderr,
                flush=True,
            )

    manifest.update(
        {
            "manifest_schema_version": FACTOR_STORE_MANIFEST_VERSION,
            "kind": "moneytree_factor_store",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_panel": {
                "path": _relative_path(root, base_path),
                "rows": int(base_summary["rows"]),
                "columns": int(base_summary["columns"]),
                "schema_hash": base_summary["schema_hash"],
                "content_hash": base_summary["content_hash"],
            },
            "factor_families": factor_entries,
            "factor_dtype": dtype,
            "compression": compression,
            "compression_level": compression_level,
            "row_group_size": row_group_size,
            "key_validation": {
                "date_ticker_unique": True,
                "aligned": True,
            },
            "external_generation": sanitize_manifest_metadata(
                {
                    "families_requested": list(requested_families),
                    "families_generated": generated,
                    "families_skipped": skipped,
                    "parts_generated": parts_generated,
                    "parts_skipped": parts_skipped,
                    "source": "dolphindb",
                    "streamed": True,
                    "input_mode": "parquet_streaming",
                    "chunk_trade_dates": int(chunk_trade_dates),
                    "warmup_trade_dates": warmup,
                    "compression": compression,
                    "compression_level": compression_level,
                    "row_group_size": row_group_size,
                    **dict(metadata or {}),
                }
            ),
            "metadata": sanitize_manifest_metadata(
                {
                    **dict(manifest.get("metadata", {})),
                    **dict(metadata or {}),
                    "input_mode": "parquet_streaming",
                }
            ),
        }
    )
    sanitized_manifest = sanitize_manifest_metadata(manifest)
    manifest_path.write_text(json.dumps(sanitized_manifest, indent=2), encoding="utf-8")
    return sanitized_manifest


def write_local_factor_store(
    base_panel: pd.DataFrame,
    output_dir: str | Path,
    *,
    families: Iterable[str],
    adjusted: bool = True,
    factor_dtype: str = "float32",
    chunk_trade_dates: int = 60,
    metadata: dict[str, Any] | None = None,
    compression: str = DEFAULT_PARQUET_COMPRESSION,
    compression_level: int | None = None,
    row_group_size: int | None = None,
    overwrite: bool = False,
    show_progress: bool = False,
) -> dict[str, Any]:
    """Generate local factor families from a base panel into a partitioned factor store."""
    requested_families = _normalize_local_families(families)
    dtype = normalize_factor_dtype(factor_dtype)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    indexed = _validate_unique_date_ticker(base_panel, source_name="base panel")
    base_columns = [column for column in indexed.columns if column not in factor_columns(indexed.columns)]
    base_frame = indexed.loc[:, base_columns]

    manifest_path = root / "manifest.json"
    existing_base: pd.DataFrame | None = None
    if manifest_path.exists():
        manifest = read_factor_store_manifest(manifest_path)
        existing_base_path = _resolve_store_path(root, manifest["base_panel"]["path"])
        if existing_base_path.exists():
            existing_base = _validate_unique_date_ticker(
                load_market_data(existing_base_path),
                source_name="base panel",
            )
    else:
        manifest = new_factor_store_manifest()

    factor_entries = dict(manifest.get("factor_families", {}))
    non_requested_existing = [
        family
        for family in factor_entries
        if family not in requested_families
    ]
    base_changed_with_stale_risk = False
    if existing_base is not None and non_requested_existing:
        if not existing_base.index.equals(base_frame.index):
            base_changed_with_stale_risk = True
        elif not existing_base.equals(base_frame):
            base_changed_with_stale_risk = True
    if base_changed_with_stale_risk:
        raise FactorStoreValidationError(
            "Existing factor store base panel does not match the input panel. "
            "Request existing families so they can be incrementally updated, or use a new "
            f"output directory. Stale families: {', '.join(non_requested_existing)}."
        )

    base_path = root / "base.parquet"
    base_path.parent.mkdir(parents=True, exist_ok=True)
    save_market_data(
        base_frame,
        base_path,
        compression=compression,
        compression_level=compression_level,
        row_group_size=row_group_size,
    )

    generated: list[str] = []
    skipped: list[str] = []
    parts_generated: dict[str, int] = {}
    parts_skipped: dict[str, int] = {}
    for family in requested_families:
        existing_entry = factor_entries.get(family)
        if existing_entry is not None and not overwrite:
            _require_local_entry_compatible(
                existing_entry,
                manifest,
                family,
                adjusted=adjusted,
                factor_dtype=dtype,
                chunk_trade_dates=chunk_trade_dates,
                compression=compression,
                compression_level=compression_level,
                row_group_size=row_group_size,
            )
        result = _write_partitioned_local_family(
            base_frame,
            root,
            family,
            existing_entry=existing_entry,
            existing_base_frame=existing_base,
            overwrite=overwrite,
            adjusted=adjusted,
            factor_dtype=dtype,
            chunk_trade_dates=chunk_trade_dates,
            compression=compression,
            compression_level=compression_level,
            row_group_size=row_group_size,
            show_progress=show_progress,
        )
        factor_entries[family] = result.entry
        parts_generated[family] = result.generated_parts
        parts_skipped[family] = result.skipped_parts
        if result.generated_parts > 0:
            generated.append(family)
        else:
            skipped.append(family)

    manifest.update(
        {
            "manifest_schema_version": FACTOR_STORE_MANIFEST_VERSION,
            "kind": "moneytree_factor_store",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_panel": {
                "path": _relative_path(root, base_path),
                "rows": int(len(base_frame)),
                "columns": int(len(base_frame.columns)),
                "schema_hash": dataframe_schema_hash(base_frame),
            },
            "factor_families": factor_entries,
            "factor_dtype": dtype,
            "compression": compression,
            "compression_level": compression_level,
            "row_group_size": row_group_size,
            "local_generation": {
                "families_requested": list(requested_families),
                "families_generated": generated,
                "families_skipped": skipped,
                "parts_generated": parts_generated,
                "parts_skipped": parts_skipped,
                "adjusted": bool(adjusted),
                "chunk_trade_dates": int(chunk_trade_dates),
                "compression": compression,
                "compression_level": compression_level,
                "row_group_size": row_group_size,
            },
            "metadata": {**dict(manifest.get("metadata", {})), **dict(metadata or {})},
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def write_local_factor_store_from_parquet(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    families: Iterable[str],
    adjusted: bool = True,
    factor_dtype: str = "float32",
    chunk_trade_dates: int = 60,
    metadata: dict[str, Any] | None = None,
    compression: str = DEFAULT_PARQUET_COMPRESSION,
    compression_level: int | None = None,
    row_group_size: int | None = None,
    overwrite: bool = False,
    show_progress: bool = False,
) -> dict[str, Any]:
    """Generate local factor families from a parquet base panel without loading it all."""
    requested_families = _normalize_local_families(families)
    dtype = normalize_factor_dtype(factor_dtype)
    source_path = Path(input_path)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    schema_columns = _parquet_schema_columns(source_path)
    if not {"date", "ticker"}.issubset(schema_columns):
        raise FactorStoreValidationError("Input parquet must contain date/ticker columns or index.")

    base_data_columns = [
        column
        for column in schema_columns
        if column not in {"date", "ticker"} and column not in factor_columns(schema_columns)
    ]
    base_storage_columns = [*base_data_columns, "date", "ticker"]
    dates = _parquet_trade_dates(source_path)

    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = read_factor_store_manifest(manifest_path)
    else:
        manifest = new_factor_store_manifest()

    factor_entries = dict(manifest.get("factor_families", {}))
    non_requested_existing = [
        family
        for family in factor_entries
        if family not in requested_families
    ]

    base_path = root / "base.parquet"
    base_tmp_path = base_path.with_suffix(base_path.suffix + ".tmp")
    base_summary = _stream_copy_base_parquet(
        source_path,
        base_tmp_path,
        storage_columns=base_storage_columns,
        data_columns=base_data_columns,
        compression=compression,
        compression_level=compression_level,
        row_group_size=row_group_size,
    )

    existing_base = dict(manifest.get("base_panel", {}))
    existing_hash = existing_base.get("content_hash")
    if (
        non_requested_existing
        and existing_hash is not None
        and str(existing_hash) != str(base_summary["content_hash"])
    ):
        base_tmp_path.unlink(missing_ok=True)
        raise FactorStoreValidationError(
            "Existing factor store base panel does not match the input panel. "
            "Request existing families so they can be incrementally updated, or use a new "
            f"output directory. Stale families: {', '.join(non_requested_existing)}."
        )
    base_tmp_path.replace(base_path)

    generated: list[str] = []
    skipped: list[str] = []
    parts_generated: dict[str, int] = {}
    parts_skipped: dict[str, int] = {}
    for family in requested_families:
        existing_entry = factor_entries.get(family)
        if existing_entry is not None and not overwrite:
            _require_local_entry_compatible(
                existing_entry,
                manifest,
                family,
                adjusted=adjusted,
                factor_dtype=dtype,
                chunk_trade_dates=chunk_trade_dates,
                compression=compression,
                compression_level=compression_level,
                row_group_size=row_group_size,
            )
        result = _write_partitioned_local_family_from_parquet(
            source_path,
            root,
            family,
            dates=dates,
            schema_columns=schema_columns,
            existing_entry=existing_entry,
            manifest=manifest,
            overwrite=overwrite,
            adjusted=adjusted,
            factor_dtype=dtype,
            chunk_trade_dates=chunk_trade_dates,
            compression=compression,
            compression_level=compression_level,
            row_group_size=row_group_size,
            show_progress=show_progress,
        )
        factor_entries[family] = result.entry
        parts_generated[family] = result.generated_parts
        parts_skipped[family] = result.skipped_parts
        if result.generated_parts > 0:
            generated.append(family)
        else:
            skipped.append(family)

    manifest.update(
        {
            "manifest_schema_version": FACTOR_STORE_MANIFEST_VERSION,
            "kind": "moneytree_factor_store",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_panel": {
                "path": _relative_path(root, base_path),
                "rows": int(base_summary["rows"]),
                "columns": int(base_summary["columns"]),
                "schema_hash": base_summary["schema_hash"],
                "content_hash": base_summary["content_hash"],
            },
            "factor_families": factor_entries,
            "factor_dtype": dtype,
            "compression": compression,
            "compression_level": compression_level,
            "row_group_size": row_group_size,
            "key_validation": {
                "date_ticker_unique": True,
                "aligned": True,
            },
            "local_generation": {
                "families_requested": list(requested_families),
                "families_generated": generated,
                "families_skipped": skipped,
                "parts_generated": parts_generated,
                "parts_skipped": parts_skipped,
                "adjusted": bool(adjusted),
                "chunk_trade_dates": int(chunk_trade_dates),
                "compression": compression,
                "compression_level": compression_level,
                "row_group_size": row_group_size,
                "input_mode": "parquet_streaming",
            },
            "metadata": sanitize_manifest_metadata(
                {
                    **dict(manifest.get("metadata", {})),
                    **dict(metadata or {}),
                    "input_mode": "parquet_streaming",
                }
            ),
        }
    )
    sanitized_manifest = sanitize_manifest_metadata(manifest)
    manifest_path.write_text(json.dumps(sanitized_manifest, indent=2), encoding="utf-8")
    return sanitized_manifest


def write_external_factor_store(
    base_panel: pd.DataFrame,
    factor_panel: pd.DataFrame,
    output_dir: str | Path,
    *,
    families: Iterable[str],
    factor_dtype: str = "float32",
    chunk_trade_dates: int = 60,
    metadata: dict[str, Any] | None = None,
    compression: str = DEFAULT_PARQUET_COMPRESSION,
    compression_level: int | None = None,
    row_group_size: int | None = None,
    overwrite: bool = False,
    show_progress: bool = False,
) -> dict[str, Any]:
    """Write precomputed external Alpha101/191 families into a factor store."""
    requested_families = _normalize_families(families)
    unsupported = [family for family in requested_families if family not in EXTERNAL_FACTOR_FAMILIES]
    if unsupported:
        choices = ", ".join(EXTERNAL_FACTOR_FAMILIES)
        raise ValueError(
            f"Unsupported external factor families: {', '.join(unsupported)}. "
            f"Expected one of: {choices}."
        )
    if not requested_families:
        raise ValueError("At least one external factor family is required.")

    dtype = normalize_factor_dtype(factor_dtype)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    indexed_base = _validate_unique_date_ticker(base_panel, source_name="base panel")
    base_columns = [
        column for column in indexed_base.columns if column not in factor_columns(indexed_base.columns)
    ]
    base_frame = indexed_base.loc[:, base_columns]
    indexed_factors = _validate_unique_date_ticker(factor_panel, source_name="external factors")

    factor_frames: dict[str, pd.DataFrame] = {}
    for family in requested_families:
        expected_columns = _expected_external_family_columns(family)
        missing = [column for column in expected_columns if column not in indexed_factors.columns]
        if missing:
            raise FactorStoreValidationError(
                f"{family} factors are missing expected columns: {missing}."
            )
        factor_frames[family] = coerce_factor_columns(indexed_factors.loc[:, expected_columns], dtype)
    validate_factor_store_keys(base_frame, factor_frames)

    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = read_factor_store_manifest(manifest_path)
        existing_base_path = _resolve_store_path(root, manifest["base_panel"]["path"])
        if existing_base_path.exists():
            existing_base = _validate_unique_date_ticker(
                load_market_data(existing_base_path),
                source_name="base panel",
            )
            if not existing_base.index.equals(base_frame.index):
                raise FactorStoreValidationError(
                    "Existing factor store base panel index does not match the input panel."
                )
    else:
        manifest = new_factor_store_manifest()

    base_path = root / "base.parquet"
    save_market_data(
        base_frame,
        base_path,
        compression=compression,
        compression_level=compression_level,
        row_group_size=row_group_size,
    )

    factor_entries = dict(manifest.get("factor_families", {}))
    generated: list[str] = []
    skipped: list[str] = []
    for family, frame in factor_frames.items():
        if family in factor_entries and not overwrite:
            skipped.append(family)
            continue
        factor_entries[family] = write_partitioned_factor_family(
            frame,
            root,
            family,
            chunk_trade_dates=chunk_trade_dates,
            compression=compression,
            compression_level=compression_level,
            row_group_size=row_group_size,
            show_progress=show_progress,
            source="dolphindb",
        )
        generated.append(family)

    manifest.update(
        {
            "manifest_schema_version": FACTOR_STORE_MANIFEST_VERSION,
            "kind": "moneytree_factor_store",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_panel": {
                "path": _relative_path(root, base_path),
                "rows": int(len(base_frame)),
                "columns": int(len(base_frame.columns)),
                "schema_hash": dataframe_schema_hash(base_frame),
            },
            "factor_families": factor_entries,
            "factor_dtype": dtype,
            "compression": compression,
            "compression_level": compression_level,
            "row_group_size": row_group_size,
            "key_validation": {
                "date_ticker_unique": True,
                "aligned": True,
            },
            "external_generation": sanitize_manifest_metadata(
                {
                    "families_requested": list(requested_families),
                    "families_generated": generated,
                    "families_skipped": skipped,
                    "source": "dolphindb",
                    "chunk_trade_dates": int(chunk_trade_dates),
                    "compression": compression,
                    "compression_level": compression_level,
                    "row_group_size": row_group_size,
                    **dict(metadata or {}),
                }
            ),
            "metadata": sanitize_manifest_metadata(
                {**dict(manifest.get("metadata", {})), **dict(metadata or {})}
            ),
        }
    )
    sanitized_manifest = sanitize_manifest_metadata(manifest)
    manifest_path.write_text(json.dumps(sanitized_manifest, indent=2), encoding="utf-8")
    return sanitized_manifest


def write_factor_store(
    panel: pd.DataFrame,
    output_dir: str | Path,
    *,
    families: Iterable[str] | None = None,
    factor_dtype: str = "float32",
    metadata: dict[str, Any] | None = None,
    compression: str = DEFAULT_PARQUET_COMPRESSION,
    compression_level: int | None = None,
    row_group_size: int | None = None,
) -> dict[str, Any]:
    """Write an additive base-panel plus factor-family store and return its manifest."""
    dtype = normalize_factor_dtype(factor_dtype)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    indexed = _validate_unique_date_ticker(panel, source_name="input panel")
    requested_families = _normalize_families(families) or _families_from_columns(indexed.columns)
    if not requested_families:
        raise ValueError("No factor families found or requested for factor-store output.")

    missing = [
        family
        for family in requested_families
        if not _family_columns(indexed.columns, family)
    ]
    if missing:
        raise ValueError(f"Requested factor families are missing from input data: {', '.join(missing)}.")

    base_columns = [column for column in indexed.columns if column not in factor_columns(indexed.columns)]
    base_frame = indexed.loc[:, base_columns]
    factor_frames = {
        family: coerce_factor_columns(indexed.loc[:, _family_columns(indexed.columns, family)], dtype)
        for family in requested_families
    }
    validate_factor_store_keys(base_frame, factor_frames)

    base_path = root / "base.parquet"
    factors_dir = root / "factors"
    factors_dir.mkdir(parents=True, exist_ok=True)
    save_market_data(
        base_frame,
        base_path,
        compression=compression,
        compression_level=compression_level,
        row_group_size=row_group_size,
    )

    factor_entries: dict[str, dict[str, Any]] = {}
    for family, frame in factor_frames.items():
        factor_path = factors_dir / f"{family}.parquet"
        save_market_data(
            frame,
            factor_path,
            compression=compression,
            compression_level=compression_level,
            row_group_size=row_group_size,
        )
        factor_entries[family] = {
            "path": _relative_path(root, factor_path),
            "prefix": FACTOR_FAMILY_PREFIXES[family],
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
        }

    manifest = new_factor_store_manifest()
    manifest.update(
        {
            "base_panel": {
                "path": _relative_path(root, base_path),
                "rows": int(len(base_frame)),
                "columns": int(len(base_frame.columns)),
            },
            "factor_families": factor_entries,
            "factor_dtype": dtype,
            "compression": compression,
            "compression_level": compression_level,
            "row_group_size": row_group_size,
            "metadata": metadata or {},
        }
    )
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _families_from_prefixes(prefixes: Iterable[str] | None) -> tuple[str, ...]:
    if not prefixes:
        return ()
    requested: list[str] = []
    normalized_prefixes = {str(prefix).strip().lower().replace("-", "_") for prefix in prefixes}
    for family, prefix in FACTOR_FAMILY_PREFIXES.items():
        if family in normalized_prefixes or prefix in normalized_prefixes:
            requested.append(family)
    return tuple(requested)


def _select_manifest_families(
    manifest: dict[str, Any],
    *,
    include_factor_families: Iterable[str] | None = None,
    include_factor_prefixes: Iterable[str] | None = None,
) -> tuple[str, ...]:
    selected = _normalize_families(include_factor_families)
    prefix_selected = _families_from_prefixes(include_factor_prefixes)
    if include_factor_prefixes and not prefix_selected:
        missing = ", ".join(str(prefix) for prefix in include_factor_prefixes)
        raise FactorStoreValidationError(
            f"Requested factor prefixes are missing from factor-store manifest: {missing}."
        )
    if selected and prefix_selected:
        selected = tuple(dict.fromkeys([*selected, *prefix_selected]))
    elif prefix_selected:
        selected = prefix_selected
    if not selected:
        selected = tuple(manifest.get("factor_families", {}).keys())

    missing = [family for family in selected if family not in manifest.get("factor_families", {})]
    if missing:
        raise FactorStoreValidationError(
            f"Requested factor families are missing from factor-store manifest: {', '.join(missing)}."
        )
    return selected


def _entry_rows_for_date_range(
    entry: dict[str, Any],
    *,
    date_start: object | None,
    date_end: object | None,
) -> int:
    if not date_start and not date_end:
        return int(entry.get("rows", 0))
    parts = _part_metadata_by_path(entry)
    if not parts:
        return int(entry.get("rows", 0))
    rows = 0
    for path in _entry_paths_for_date_range(entry, date_start=date_start, date_end=date_end):
        rows += int(parts.get(path, {}).get("rows", 0))
    return rows


def estimate_factor_store_load_memory(
    manifest_path: str | Path,
    *,
    include_factor_families: Iterable[str] | None = None,
    include_factor_prefixes: Iterable[str] | None = None,
    date_start: object | None = None,
    date_end: object | None = None,
    per_cell_bytes: int = 16,
    copy_factor: float = 3.0,
) -> FactorStoreLoadEstimate:
    """Estimate peak in-memory size for loading selected factor-store families."""
    manifest = read_factor_store_manifest(manifest_path)

    selected = _select_manifest_families(
        manifest,
        include_factor_families=include_factor_families,
        include_factor_prefixes=include_factor_prefixes,
    )
    base_panel = dict(manifest.get("base_panel", {}))
    row_candidates = [int(base_panel.get("rows", 0))]
    if date_start or date_end:
        row_candidates = []
    for family in selected:
        row_candidates.append(
            _entry_rows_for_date_range(
                manifest["factor_families"][family],
                date_start=date_start,
                date_end=date_end,
            )
        )
    rows = max(row_candidates) if row_candidates else int(base_panel.get("rows", 0))
    columns = int(base_panel.get("columns", 0)) + sum(
        int(manifest["factor_families"][family].get("columns", 0)) for family in selected
    )
    required = int(max(0, rows) * max(1, columns) * int(per_cell_bytes) * float(copy_factor))
    return FactorStoreLoadEstimate(
        rows=int(rows),
        columns=int(columns),
        selected_families=tuple(selected),
        required_bytes=required,
    )


def load_factor_store(
    manifest_path: str | Path,
    *,
    include_factor_families: Iterable[str] | None = None,
    include_factor_prefixes: Iterable[str] | None = None,
    date_start: object | None = None,
    date_end: object | None = None,
) -> pd.DataFrame:
    """Load a factor-store manifest and join selected factor families to the base panel."""
    manifest_file = Path(manifest_path)
    manifest = read_factor_store_manifest(manifest_file)

    root = manifest_file.parent
    base_path = _resolve_store_path(root, str(manifest["base_panel"]["path"]))
    base_frame = _validate_unique_date_ticker(
        load_market_data(base_path, date_start=date_start, date_end=date_end),
        source_name="base panel",
    )
    selected = _select_manifest_families(
        manifest,
        include_factor_families=include_factor_families,
        include_factor_prefixes=include_factor_prefixes,
    )

    out = base_frame.copy()
    factor_frames: dict[str, pd.DataFrame] = {}
    for family in selected:
        entry = manifest["factor_families"][family]
        frame = _validate_unique_date_ticker(
            _read_factor_entry(root, entry, date_start=date_start, date_end=date_end),
            source_name=f"{family} factors",
        )
        factor_frames[family] = frame
    validate_factor_store_keys(base_frame, factor_frames)
    for frame in factor_frames.values():
        out = out.join(frame, how="left")
    return out
