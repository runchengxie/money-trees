from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moneytree._factor_store_validation import FactorStoreValidationError

FACTOR_STORE_MANIFEST_VERSION = "1.0"


def new_factor_store_manifest() -> dict[str, Any]:
    return {
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


def read_factor_store_manifest(manifest_path: str | Path) -> dict[str, Any]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("manifest_schema_version") != FACTOR_STORE_MANIFEST_VERSION:
        raise FactorStoreValidationError("Unsupported factor-store manifest schema version.")
    return manifest


def _entry_option(
    entry: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
    key: str,
    *,
    local_key: str | None = None,
) -> Any:
    if entry is not None and key in entry:
        return entry[key]
    local_generation = dict((manifest or {}).get("local_generation", {}))
    lookup_key = local_key or key
    if lookup_key in local_generation:
        return local_generation[lookup_key]
    return (manifest or {}).get(key)


def _normalize_comparable_option(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return value


def _require_local_entry_compatible(
    entry: dict[str, Any],
    manifest: dict[str, Any],
    family: str,
    *,
    adjusted: bool,
    factor_dtype: str,
    chunk_trade_dates: int,
    compression: str,
    compression_level: int | None,
    row_group_size: int | None,
) -> None:
    if not entry.get("partitioned") or not entry.get("paths"):
        raise FactorStoreValidationError(
            f"Existing {family} factor entry is not partitioned; use --overwrite to regenerate it."
        )

    expected = {
        "factor_dtype": factor_dtype,
        "adjusted": bool(adjusted),
        "chunk_trade_dates": int(chunk_trade_dates),
        "compression": compression,
        "compression_level": compression_level,
        "row_group_size": row_group_size,
    }
    found = {
        "factor_dtype": _entry_option(entry, manifest, "factor_dtype"),
        "adjusted": _entry_option(entry, manifest, "adjusted"),
        "chunk_trade_dates": _entry_option(entry, manifest, "chunk_trade_dates"),
        "compression": _entry_option(entry, manifest, "compression"),
        "compression_level": _entry_option(entry, manifest, "compression_level"),
        "row_group_size": _entry_option(entry, manifest, "row_group_size"),
    }
    if found["chunk_trade_dates"] is not None:
        found["chunk_trade_dates"] = int(found["chunk_trade_dates"])
    if found["adjusted"] is not None:
        found["adjusted"] = bool(found["adjusted"])

    mismatches = [
        key
        for key, expected_value in expected.items()
        if _normalize_comparable_option(found.get(key))
        != _normalize_comparable_option(expected_value)
    ]
    if mismatches:
        details = ", ".join(
            f"{key}: existing={found.get(key)!r} requested={expected[key]!r}"
            for key in mismatches
        )
        raise FactorStoreValidationError(
            f"Existing {family} factors were generated with different options ({details}); "
            "use --overwrite to regenerate them."
        )


def _part_metadata_by_path(entry: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    parts = (entry or {}).get("parts", [])
    if not isinstance(parts, list):
        return {}
    return {
        str(part["path"]): part
        for part in parts
        if isinstance(part, dict) and part.get("path")
    }
