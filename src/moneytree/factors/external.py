from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from moneytree.metadata import (
    dataframe_metadata,
    file_metadata,
    runtime_metadata,
    stable_json_dumps,
)

EXTERNAL_ALPHA_COUNTS = {
    "alpha101": 101,
    "alpha191": 191,
}
EXTERNAL_ALPHA_PREFIXES = tuple(EXTERNAL_ALPHA_COUNTS)
EXTERNAL_ALPHA_MANIFEST_SCHEMA_VERSION = "1.0"


class ExternalAlphaError(ValueError):
    """Base error for external alpha contract failures."""


class UnsupportedExternalAlphaFamilyError(ExternalAlphaError):
    """Raised when a requested external alpha family is not supported."""


class ExternalAlphaInputError(ExternalAlphaError):
    """Raised when the input panel cannot satisfy the external alpha contract."""


class ExternalAlphaValidationError(ExternalAlphaError):
    """Raised when generated external alpha output violates the contract."""


@dataclass(frozen=True)
class FieldMapping:
    target: str
    preferred: list[str]
    selected: str | None
    required: bool
    fallback_used: bool = False
    transform: str | None = None
    note: str | None = None


def normalize_external_family(family: str) -> str:
    key = family.strip().lower().replace("-", "_")
    if key not in EXTERNAL_ALPHA_COUNTS:
        available = ", ".join(sorted(EXTERNAL_ALPHA_COUNTS))
        raise UnsupportedExternalAlphaFamilyError(
            f"Unsupported external alpha family '{family}'. Available: {available}."
        )
    return key


def normalize_external_families(families: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for family in families:
        key = normalize_external_family(family)
        if key not in normalized:
            normalized.append(key)
    if not normalized:
        available = ", ".join(sorted(EXTERNAL_ALPHA_COUNTS))
        raise UnsupportedExternalAlphaFamilyError(
            f"At least one external alpha family is required. Available: {available}."
        )
    return normalized


def external_alpha_columns(family: str) -> list[str]:
    key = normalize_external_family(family)
    return [f"{key}_{idx:03d}" for idx in range(1, EXTERNAL_ALPHA_COUNTS[key] + 1)]


def requested_external_alpha_columns(families: Iterable[str]) -> list[str]:
    columns: list[str] = []
    for family in normalize_external_families(families):
        columns.extend(external_alpha_columns(family))
    return columns


def _with_date_ticker_columns(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    out = frame.copy()

    if isinstance(out.index, pd.MultiIndex) and {"date", "ticker"}.issubset(
        set(out.index.names)
    ):
        out = out.copy()
        out["date"] = out.index.get_level_values("date")
        out["ticker"] = out.index.get_level_values("ticker")
        return out.reset_index(drop=True)

    if {"date", "ticker"}.issubset(out.columns):
        return out

    if {"tradetime", "securityid"}.issubset(out.columns):
        out = out.rename(columns={"tradetime": "date", "securityid": "ticker"})
        return out

    raise ExternalAlphaInputError(
        f"{source_name} must contain date/ticker columns, a date/ticker MultiIndex, "
        "or DolphinDB tradetime/securityid columns."
    )


def normalize_date_ticker_frame(frame: pd.DataFrame, source_name: str = "frame") -> pd.DataFrame:
    out = _with_date_ticker_columns(frame, source_name).copy()
    out["date"] = pd.to_datetime(out["date"], errors="raise")
    out["ticker"] = out["ticker"].astype(str)
    validate_date_ticker_keys(out, source_name=source_name)
    return out.set_index(["date", "ticker"]).sort_index()


def validate_date_ticker_keys(frame: pd.DataFrame, source_name: str = "frame") -> None:
    keyed = _with_date_ticker_columns(frame, source_name)
    duplicate_mask = keyed.duplicated(subset=["date", "ticker"], keep=False)
    if duplicate_mask.any():
        sample = keyed.loc[duplicate_mask, ["date", "ticker"]].head(5).to_dict("records")
        raise ExternalAlphaValidationError(
            f"{source_name} contains duplicate date/ticker keys. Sample: {sample}"
        )


def validate_external_alpha_columns(frame: pd.DataFrame, families: Iterable[str]) -> dict[str, Any]:
    normalized_families = normalize_external_families(families)
    expected = set(requested_external_alpha_columns(normalized_families))
    observed = {
        str(column)
        for column in frame.columns
        if str(column).startswith(EXTERNAL_ALPHA_PREFIXES)
    }
    missing = sorted(expected.difference(observed))
    unexpected = sorted(observed.difference(expected))

    if missing or unexpected:
        parts: list[str] = []
        if missing:
            parts.append(f"missing columns: {missing[:10]}{'...' if len(missing) > 10 else ''}")
        if unexpected:
            parts.append(
                f"unexpected alpha columns: {unexpected[:10]}"
                f"{'...' if len(unexpected) > 10 else ''}"
            )
        raise ExternalAlphaValidationError("; ".join(parts))

    return {
        "families": normalized_families,
        "expected_alpha_columns": len(expected),
        "observed_alpha_columns": len(observed),
        "missing_alpha_columns": [],
        "unexpected_alpha_columns": [],
    }


def merge_external_alpha_columns(
    panel: pd.DataFrame,
    alpha_frame: pd.DataFrame,
    families: Iterable[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    normalized_families = normalize_external_families(families)
    base = normalize_date_ticker_frame(panel, source_name="input panel")
    generated = normalize_date_ticker_frame(alpha_frame, source_name="external alpha output")
    column_summary = validate_external_alpha_columns(generated, normalized_families)
    alpha_columns = requested_external_alpha_columns(normalized_families)

    base_keys = base.index
    generated_keys = generated.index
    extra_keys = generated_keys.difference(base_keys)
    if len(extra_keys) > 0:
        sample = [
            {"date": pd.Timestamp(date).isoformat(), "ticker": ticker}
            for date, ticker in list(extra_keys[:5])
        ]
        raise ExternalAlphaValidationError(
            f"external alpha output contains keys outside the input panel. Sample: {sample}"
        )

    matched_keys = generated_keys.intersection(base_keys)
    if len(matched_keys) == 0:
        raise ExternalAlphaValidationError(
            "external alpha output has no date/ticker keys matching the input panel."
        )

    matched_values = generated.loc[matched_keys, alpha_columns]
    if not bool(matched_values.notna().to_numpy().any()):
        raise ExternalAlphaValidationError(
            "external alpha output has no non-null requested alpha values for matching keys."
        )

    merged = base.join(generated[alpha_columns], how="left")
    validation_summary = {
        **column_summary,
        "input_rows": int(len(base)),
        "external_rows": int(len(generated)),
        "output_rows": int(len(merged)),
        "matched_external_rows": int(len(matched_keys)),
        "unmatched_external_rows": int(len(extra_keys)),
        "input_rows_without_external_values": int(len(base_keys.difference(generated_keys))),
        "non_null_alpha_values": int(merged[alpha_columns].notna().sum().sum()),
    }
    return merged, validation_summary


def _field_mapping_dict(mapping: FieldMapping) -> dict[str, Any]:
    return asdict(mapping)


def _select_series(
    panel: pd.DataFrame,
    target: str,
    preferred: list[str],
    *,
    required: bool,
    default: Any = np.nan,
    transform: str | None = None,
    note: str | None = None,
) -> tuple[pd.Series, FieldMapping]:
    for idx, column in enumerate(preferred):
        if column in panel.columns:
            series = panel[column]
            if transform == "tushare_lots_to_shares" and idx > 0:
                series = series.astype(float) * 100.0
            return (
                series,
                FieldMapping(
                    target=target,
                    preferred=preferred,
                    selected=column,
                    required=required,
                    fallback_used=idx > 0,
                    transform=transform if idx > 0 else None,
                    note=note,
                ),
            )

    if required:
        raise ExternalAlphaInputError(
            f"Missing required input for {target}: expected one of {preferred}."
        )

    return (
        pd.Series(default, index=panel.index),
        FieldMapping(
            target=target,
            preferred=preferred,
            selected=None,
            required=required,
            fallback_used=True,
            note=note,
        ),
    )


def build_dolphindb_input(
    panel: pd.DataFrame,
    families: Iterable[str],
    *,
    use_adjusted_prices: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    normalized_families = normalize_external_families(families)
    source = normalize_date_ticker_frame(panel, source_name="input panel")
    fields: dict[str, FieldMapping] = {}

    out = pd.DataFrame(index=source.index)
    out["tradetime"] = source.index.get_level_values("date")
    out["securityid"] = source.index.get_level_values("ticker").astype(str)

    for field in ("open", "high", "low", "close", "vwap"):
        preferred = [f"{field}_adj", field] if use_adjusted_prices else [field]
        series, mapping = _select_series(source, field, preferred, required=True)
        out[field] = series.astype(float)
        fields[field] = mapping

    volume, volume_mapping = _select_series(
        source,
        "vol",
        ["volume", "vol"],
        required=True,
        transform="tushare_lots_to_shares",
    )
    out["vol"] = volume.astype(float)
    fields["vol"] = volume_mapping

    cap, cap_mapping = _select_series(
        source,
        "cap",
        ["circ_mv", "total_mv"],
        required=False,
        default=np.nan,
        note="Market-cap field is required by a subset of Alpha101 formulas.",
    )
    out["cap"] = cap.astype(float)
    fields["cap"] = cap_mapping

    industry, industry_mapping = _select_series(
        source,
        "indclass",
        ["industry"],
        required=False,
        default="UNKNOWN",
        note="Industry field should be point-in-time for industry-aware Alpha101 formulas.",
    )
    out["indclass"] = industry.fillna("UNKNOWN").astype(str)
    fields["indclass"] = industry_mapping

    benchmark_required = "alpha191" in normalized_families
    index_open, index_open_mapping = _select_series(
        source,
        "index_open",
        ["benchmark_open"],
        required=benchmark_required,
        default=np.nan,
    )
    index_close, index_close_mapping = _select_series(
        source,
        "index_close",
        ["benchmark_close"],
        required=benchmark_required,
        default=np.nan,
    )
    out["index_open"] = index_open.astype(float)
    out["index_close"] = index_close.astype(float)
    fields["index_open"] = index_open_mapping
    fields["index_close"] = index_close_mapping

    out = out.reset_index(drop=True)
    summary = {
        "families": normalized_families,
        "use_adjusted_prices": bool(use_adjusted_prices),
        "fields": {target: _field_mapping_dict(mapping) for target, mapping in fields.items()},
        "fallback_fields": [
            mapping.target
            for mapping in fields.values()
            if mapping.fallback_used and mapping.selected is not None
        ],
        "missing_optional_fields": [
            mapping.target
            for mapping in fields.values()
            if mapping.selected is None and not mapping.required
        ],
    }
    return out, summary


_SECRET_KEY_PARTS = ("password", "token", "secret", "api_key", "apikey")


def sanitize_manifest_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lower = key_text.lower()
            if any(part in lower for part in _SECRET_KEY_PARTS):
                continue
            sanitized[key_text] = sanitize_manifest_metadata(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_manifest_metadata(item) for item in value]
    return value


def build_external_alpha_manifest(
    *,
    input_path: str | Path,
    output_path: str | Path,
    input_frame: pd.DataFrame,
    output_frame: pd.DataFrame,
    families: Iterable[str],
    field_mapping: dict[str, Any],
    validation: dict[str, Any],
    dolphindb: dict[str, Any],
    module_versions: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    normalized_families = normalize_external_families(families)
    generated_at = generated_at_utc or datetime.now(timezone.utc).isoformat()
    module_versions = module_versions or {}

    manifest = {
        "manifest_schema_version": EXTERNAL_ALPHA_MANIFEST_SCHEMA_VERSION,
        "factor_source": "dolphindb",
        "generated_at_utc": generated_at,
        "families": normalized_families,
        "generated_columns": {
            family: external_alpha_columns(family) for family in normalized_families
        },
        "input_data": file_metadata(input_path),
        "output_data": file_metadata(output_path),
        "schemas": {
            "input": dataframe_metadata(normalize_date_ticker_frame(input_frame, "input panel")),
            "output": dataframe_metadata(output_frame),
        },
        "dolphindb": sanitize_manifest_metadata(dolphindb),
        "module_versions": sanitize_manifest_metadata(module_versions),
        "field_mapping": sanitize_manifest_metadata(field_mapping),
        "validation": sanitize_manifest_metadata(validation),
        "runtime": runtime_metadata(),
    }
    return sanitize_manifest_metadata(manifest)


def write_external_alpha_manifest(manifest: dict[str, Any], path: str | Path) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(stable_json_dumps(manifest) + "\n", encoding="utf-8")


def manifest_contains_secret_text(manifest: dict[str, Any], secret_text: str) -> bool:
    """Test helper for verifying secret values are not serialized."""
    return secret_text in json.dumps(manifest, ensure_ascii=False, sort_keys=True, default=str)
