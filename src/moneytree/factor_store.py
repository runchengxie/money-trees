from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable

import pandas as pd

from moneytree.data import (
    DEFAULT_PARQUET_COMPRESSION,
    FACTOR_FAMILY_PREFIXES,
    coerce_factor_columns,
    ensure_date_ticker_index,
    factor_columns,
    load_market_data,
    normalize_factor_dtype,
    save_market_data,
)
from moneytree.factors.qlib import build_alpha158_features, build_alpha360_features
from moneytree.metadata import dataframe_schema_hash

FACTOR_STORE_MANIFEST_VERSION = "1.0"
LOCAL_FACTOR_FAMILIES = ("alpha158", "alpha360")


class FactorStoreValidationError(ValueError):
    """Raised when factor-store files cannot be aligned on date/ticker."""


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


def _relative_path(base_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def _resolve_store_path(root: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else root / path


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


def _read_factor_entry(root: Path, entry: dict[str, Any]) -> pd.DataFrame:
    if "paths" in entry:
        frames = [
            load_market_data(_resolve_store_path(root, path))
            for path in entry.get("paths", [])
        ]
        if not frames:
            return pd.DataFrame()
        return ensure_date_ticker_index(pd.concat(frames, axis=0)).sort_index()
    return load_market_data(_resolve_store_path(root, str(entry["path"])))


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
    adjusted: bool,
    factor_dtype: str,
    chunk_trade_dates: int,
    compression: str,
    compression_level: int | None,
    show_progress: bool,
) -> dict[str, Any]:
    dates = pd.Index(base_frame.index.get_level_values("date").unique()).sort_values()
    chunks = _date_chunks(dates, chunk_trade_dates)
    overlap = _family_overlap(family)
    family_dir = root / "factors" / family
    family_dir.mkdir(parents=True, exist_ok=True)

    date_index = base_frame.index.get_level_values("date")
    paths: list[str] = []
    rows = 0
    columns = 0
    for idx, target_dates in enumerate(chunks, start=1):
        target_start = (idx - 1) * max(1, int(chunk_trade_dates))
        calc_start = max(0, target_start - overlap)
        calc_dates = dates[calc_start : target_start + len(target_dates)]
        calc_panel = base_frame.loc[date_index.isin(calc_dates)]
        features = _build_local_family_features(
            calc_panel,
            family,
            adjusted=adjusted,
            dtype=factor_dtype,
        )
        target_mask = features.index.get_level_values("date").isin(target_dates)
        target_features = features.loc[target_mask].sort_index()

        part_path = family_dir / f"part-{idx:04d}.parquet"
        save_market_data(
            target_features,
            part_path,
            compression=compression,
            compression_level=compression_level,
        )
        paths.append(_relative_path(root, part_path))
        rows += int(len(target_features))
        columns = int(len(target_features.columns))

        if show_progress:
            start_value = pd.Timestamp(target_dates[0]).date()
            end_value = pd.Timestamp(target_dates[-1]).date()
            print(
                (
                    f"[factor-store:{family}] part={idx}/{len(chunks)} "
                    f"rows={rows} start={start_value} end={end_value}"
                ),
                file=sys.stderr,
                flush=True,
            )

    return {
        "paths": paths,
        "partitioned": True,
        "prefix": FACTOR_FAMILY_PREFIXES[family],
        "rows": rows,
        "columns": columns,
        "chunk_trade_dates": int(chunk_trade_dates),
    }


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
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("manifest_schema_version") != FACTOR_STORE_MANIFEST_VERSION:
            raise FactorStoreValidationError("Unsupported factor-store manifest schema version.")
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
        manifest = {
            "manifest_schema_version": FACTOR_STORE_MANIFEST_VERSION,
            "kind": "moneytree_factor_store",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "factor_families": {},
            "key_validation": {
                "date_ticker_unique": True,
                "aligned": True,
            },
            "metadata": {},
        }

    base_path = root / "base.parquet"
    base_path.parent.mkdir(parents=True, exist_ok=True)
    save_market_data(
        base_frame,
        base_path,
        compression=compression,
        compression_level=compression_level,
    )

    factor_entries = dict(manifest.get("factor_families", {}))
    generated: list[str] = []
    skipped: list[str] = []
    for family in requested_families:
        if family in factor_entries and not overwrite:
            skipped.append(family)
            continue
        factor_entries[family] = _write_partitioned_local_family(
            base_frame,
            root,
            family,
            adjusted=adjusted,
            factor_dtype=dtype,
            chunk_trade_dates=chunk_trade_dates,
            compression=compression,
            compression_level=compression_level,
            show_progress=show_progress,
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
            "local_generation": {
                "families_requested": list(requested_families),
                "families_generated": generated,
                "families_skipped": skipped,
                "adjusted": bool(adjusted),
                "chunk_trade_dates": int(chunk_trade_dates),
                "compression": compression,
                "compression_level": compression_level,
            },
            "metadata": {**dict(manifest.get("metadata", {})), **dict(metadata or {})},
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def write_factor_store(
    panel: pd.DataFrame,
    output_dir: str | Path,
    *,
    families: Iterable[str] | None = None,
    factor_dtype: str = "float32",
    metadata: dict[str, Any] | None = None,
    compression: str = DEFAULT_PARQUET_COMPRESSION,
    compression_level: int | None = None,
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
    )

    factor_entries: dict[str, dict[str, Any]] = {}
    for family, frame in factor_frames.items():
        factor_path = factors_dir / f"{family}.parquet"
        save_market_data(
            frame,
            factor_path,
            compression=compression,
            compression_level=compression_level,
        )
        factor_entries[family] = {
            "path": _relative_path(root, factor_path),
            "prefix": FACTOR_FAMILY_PREFIXES[family],
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
        }

    manifest = {
        "manifest_schema_version": FACTOR_STORE_MANIFEST_VERSION,
        "kind": "moneytree_factor_store",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_panel": {
            "path": _relative_path(root, base_path),
            "rows": int(len(base_frame)),
            "columns": int(len(base_frame.columns)),
        },
        "factor_families": factor_entries,
        "factor_dtype": dtype,
        "compression": compression,
        "compression_level": compression_level,
        "key_validation": {
            "date_ticker_unique": True,
            "aligned": True,
        },
        "metadata": metadata or {},
    }
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


def load_factor_store(
    manifest_path: str | Path,
    *,
    include_factor_families: Iterable[str] | None = None,
    include_factor_prefixes: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Load a factor-store manifest and join selected factor families to the base panel."""
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("manifest_schema_version") != FACTOR_STORE_MANIFEST_VERSION:
        raise FactorStoreValidationError("Unsupported factor-store manifest schema version.")

    root = manifest_file.parent
    base_path = _resolve_store_path(root, str(manifest["base_panel"]["path"]))
    base_frame = _validate_unique_date_ticker(load_market_data(base_path), source_name="base panel")

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

    out = base_frame.copy()
    factor_frames: dict[str, pd.DataFrame] = {}
    for family in selected:
        entry = manifest["factor_families"][family]
        frame = _validate_unique_date_ticker(
            _read_factor_entry(root, entry),
            source_name=f"{family} factors",
        )
        factor_frames[family] = frame
    validate_factor_store_keys(base_frame, factor_frames)
    for frame in factor_frames.values():
        out = out.join(frame, how="left")
    return out
