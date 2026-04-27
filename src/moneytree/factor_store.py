from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from moneytree.data import (
    FACTOR_FAMILY_PREFIXES,
    coerce_factor_columns,
    ensure_date_ticker_index,
    factor_columns,
    load_market_data,
    normalize_factor_dtype,
)

FACTOR_STORE_MANIFEST_VERSION = "1.0"


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


def write_factor_store(
    panel: pd.DataFrame,
    output_dir: str | Path,
    *,
    families: Iterable[str] | None = None,
    factor_dtype: str = "float32",
    metadata: dict[str, Any] | None = None,
    compression: str = "snappy",
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
    base_frame.to_parquet(base_path, compression=compression, index=True)

    factor_entries: dict[str, dict[str, Any]] = {}
    for family, frame in factor_frames.items():
        factor_path = factors_dir / f"{family}.parquet"
        frame.to_parquet(factor_path, compression=compression, index=True)
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
    base_path = root / str(manifest["base_panel"]["path"])
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
            load_market_data(root / str(entry["path"])),
            source_name=f"{family} factors",
        )
        factor_frames[family] = frame
    validate_factor_store_keys(base_frame, factor_frames)
    for frame in factor_frames.values():
        out = out.join(frame, how="left")
    return out
