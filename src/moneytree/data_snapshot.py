from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

import pandas as pd

from moneytree.data import load_market_data
from moneytree.data_status import build_data_status_report
from moneytree.metadata import file_metadata, stable_json_hash


DATA_SNAPSHOT_SCHEMA_VERSION = "1.0"
DATA_SNAPSHOT_KIND = "moneytree_data_snapshot"


@dataclass(frozen=True)
class DataSnapshotResult:
    manifest_path: Path
    checksums_path: Path
    readme_path: Path
    manifest: dict[str, Any]


def _format_timestamp(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.time() == pd.Timestamp(0).time():
        return timestamp.date().isoformat()
    return timestamp.isoformat()


def _arrow_schema_payload(schema: Any) -> dict[str, Any]:
    columns = [
        {
            "name": str(field.name),
            "dtype": str(field.type),
            "nullable": bool(field.nullable),
        }
        for field in schema
    ]
    return {
        "format": "pyarrow",
        "columns": columns,
    }


def _parquet_panel_summary(path: Path, *, batch_size: int = 250_000) -> dict[str, Any]:
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - pyarrow is a core dependency
        raise RuntimeError("Parquet snapshot inspection requires the pyarrow dependency.") from exc

    parquet_file = pq.ParquetFile(path)
    schema = parquet_file.schema_arrow
    schema_payload = _arrow_schema_payload(schema)
    schema_names = set(schema.names)

    date_min: pd.Timestamp | None = None
    date_max: pd.Timestamp | None = None
    date_values: set[Any] = set()
    tickers: set[str] = set()

    scan_columns = [column for column in ("date", "ticker") if column in schema_names]
    if scan_columns:
        for batch in parquet_file.iter_batches(batch_size=batch_size, columns=scan_columns):
            names = batch.schema.names
            if "date" in names:
                date_array = batch.column(names.index("date"))
                parsed = pd.to_datetime(date_array.to_pandas(), errors="coerce")
                parsed = parsed.dropna()
                if not parsed.empty:
                    current_min = pd.Timestamp(parsed.min())
                    current_max = pd.Timestamp(parsed.max())
                    date_min = current_min if date_min is None else min(date_min, current_min)
                    date_max = current_max if date_max is None else max(date_max, current_max)
                    date_values.update(pd.Timestamp(value).date().isoformat() for value in parsed.unique())
            if "ticker" in names:
                ticker_array = batch.column(names.index("ticker"))
                ticker_series = ticker_array.to_pandas()
                tickers.update(str(value) for value in ticker_series.dropna().unique())

    return {
        "format": "parquet",
        "rows": int(parquet_file.metadata.num_rows),
        "columns": int(len(schema.names)),
        "row_groups": int(parquet_file.metadata.num_row_groups),
        "date_min": _format_timestamp(date_min),
        "date_max": _format_timestamp(date_max),
        "date_count": int(len(date_values)) if "date" in schema_names else None,
        "ticker_count": int(len(tickers)) if "ticker" in schema_names else None,
        "schema": schema_payload,
        "schema_hash": stable_json_hash(schema_payload),
    }


def _frame_panel_summary(path: Path) -> dict[str, Any]:
    frame = load_market_data(path)
    if isinstance(frame.index, pd.MultiIndex) and "date" in frame.index.names:
        dates = pd.to_datetime(frame.index.get_level_values("date"), errors="coerce")
    elif "date" in frame.columns:
        dates = pd.to_datetime(frame["date"], errors="coerce")
    else:
        dates = pd.Series(dtype="datetime64[ns]")

    if isinstance(frame.index, pd.MultiIndex) and "ticker" in frame.index.names:
        ticker_values = frame.index.get_level_values("ticker")
    elif "ticker" in frame.columns:
        ticker_values = frame["ticker"]
    else:
        ticker_values = pd.Series(dtype="object")

    if isinstance(frame.index, pd.MultiIndex):
        index_schema = [
            {
                "name": str(name) if name is not None else "",
                "dtype": str(frame.index.get_level_values(level).dtype),
            }
            for level, name in enumerate(frame.index.names)
        ]
    else:
        index_schema = [
            {
                "name": str(frame.index.name) if frame.index.name is not None else "",
                "dtype": str(frame.index.dtype),
            }
        ]
    schema_payload = {
        "format": "pandas",
        "index": index_schema,
        "columns": [
            {"name": str(column), "dtype": str(dtype)}
            for column, dtype in frame.dtypes.items()
        ],
    }
    valid_dates = pd.Series(dates).dropna()
    return {
        "format": path.suffix.lower().lstrip(".") or "unknown",
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "row_groups": None,
        "date_min": _format_timestamp(valid_dates.min()) if not valid_dates.empty else None,
        "date_max": _format_timestamp(valid_dates.max()) if not valid_dates.empty else None,
        "date_count": int(pd.Index(valid_dates).nunique()) if not valid_dates.empty else None,
        "ticker_count": int(pd.Index(ticker_values).nunique()) if len(ticker_values) else None,
        "schema": schema_payload,
        "schema_hash": stable_json_hash(schema_payload),
    }


def _panel_summary(path: str | Path) -> dict[str, Any]:
    panel_path = Path(path)
    if not panel_path.exists():
        raise FileNotFoundError(f"panel path does not exist: {panel_path}")
    payload = file_metadata(panel_path)
    if panel_path.suffix.lower() == ".parquet":
        payload.update(_parquet_panel_summary(panel_path))
    else:
        payload.update(_frame_panel_summary(panel_path))
    return payload


def _git_metadata(cwd: Path) -> dict[str, Any]:
    def run_git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            return None
        return result.stdout.strip()

    root = run_git("rev-parse", "--show-toplevel")
    commit = run_git("rev-parse", "HEAD")
    status = run_git("status", "--short")
    return {
        "root": root,
        "commit": commit,
        "dirty": bool(status),
    }


def _optional_layer(name: str, path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    report = build_data_status_report(**{name: path})
    layer_name = "base_panel" if name == "panel" else name
    return report.layers[layer_name]


def _checksum_entries(
    *,
    panel: dict[str, Any],
    raw_cache: dict[str, Any] | None,
    factor_store: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    entries = [
        {
            "role": "panel",
            "path": panel["path"],
            "sha256": panel["sha256"],
        }
    ]
    if raw_cache is not None and raw_cache.get("manifest_exists"):
        manifest_path = Path(str(raw_cache["manifest_path"]))
        entries.append(
            {
                "role": "raw_cache_manifest",
                "path": str(manifest_path),
                "sha256": file_metadata(manifest_path)["sha256"],
            }
        )
    if factor_store is not None and factor_store.get("manifest_exists"):
        manifest_path = Path(str(factor_store["manifest_path"]))
        entries.append(
            {
                "role": "factor_store_manifest",
                "path": str(manifest_path),
                "sha256": file_metadata(manifest_path)["sha256"],
            }
        )
    return entries


def _compact_quality_summary(
    *,
    panel: dict[str, Any],
    raw_cache: dict[str, Any] | None,
) -> dict[str, Any]:
    derived = panel.get("derived_return_checks", {})
    adjusted = panel.get("adjusted_price_checks", {})
    raw_anomalies = raw_cache.get("anomalies", []) if raw_cache is not None else []
    errors = list(panel.get("errors", []))
    warnings = list(panel.get("warnings", []))
    if raw_cache is not None:
        errors.extend(str(error) for error in raw_cache.get("errors", []))
        warnings.extend(str(warning) for warning in raw_cache.get("warnings", []))
    return {
        "status": "ok" if not errors else "error",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "duplicate_key_count": panel.get("duplicate_key_count"),
        "missing_required_columns": panel.get("missing_required_columns", []),
        "null_counts": panel.get("null_counts", {}),
        "derived_return_checks": {
            key: derived.get(key)
            for key in (
                "return_1d",
                "next_period_return",
                "benchmark_return",
                "benchmark_next_period_return",
            )
            if key in derived
        },
        "adjusted_price_checks": {
            "null_counts": adjusted.get("null_counts", {}),
            "mismatch_counts": adjusted.get("mismatch_counts", {}),
        },
        "raw_cache_anomalies": raw_anomalies,
        "errors": errors,
        "warnings": warnings,
    }


def _write_checksums(path: Path, checksums: list[dict[str, Any]]) -> None:
    lines = [
        f"{entry['sha256']}  {entry['path']}"
        for entry in checksums
        if entry.get("sha256")
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_readme(path: Path, manifest: dict[str, Any]) -> None:
    panel = manifest["panel"]
    references = manifest.get("references", {})
    raw_cache = references.get("raw_cache")
    factor_store = references.get("factor_store")
    lines = [
        "# Money Trees Data Snapshot",
        "",
        f"- Created at UTC: {manifest['created_at_utc']}",
        f"- Panel: `{panel['path']}`",
        f"- Rows: {panel.get('rows')}",
        f"- Columns: {panel.get('columns')}",
        f"- Dates: {panel.get('date_min') or 'NA'} to {panel.get('date_max') or 'NA'}",
        f"- Tickers: {panel.get('ticker_count') or 'NA'}",
        f"- Panel SHA-256: `{panel.get('sha256')}`",
    ]
    if manifest.get("label"):
        lines.append(f"- Label: {manifest['label']}")
    if raw_cache is not None:
        lines.append(f"- Raw cache manifest: `{raw_cache.get('manifest_path')}`")
    if factor_store is not None:
        lines.append(f"- Factor store manifest: `{factor_store.get('manifest_path')}`")
    if manifest.get("notes"):
        lines.extend(["", "## Notes", "", *[f"- {note}" for note in manifest["notes"]]])
    lines.extend(
        [
            "",
            "This snapshot records metadata and checksums only. It does not copy large data files.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def create_data_snapshot(
    *,
    panel: str | Path,
    output_dir: str | Path,
    raw_cache: str | Path | None = None,
    factor_store: str | Path | None = None,
    label: str | None = None,
    notes: list[str] | None = None,
) -> DataSnapshotResult:
    """Write metadata and checksum files for a Money Trees data snapshot."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    panel_payload = _panel_summary(panel)
    panel_quality_payload = _optional_layer("panel", Path(panel))
    raw_cache_payload = _optional_layer("raw_cache", Path(raw_cache) if raw_cache else None)
    factor_store_payload = _optional_layer(
        "factor_store",
        Path(factor_store) if factor_store else None,
    )
    checksums = _checksum_entries(
        panel=panel_payload,
        raw_cache=raw_cache_payload,
        factor_store=factor_store_payload,
    )
    manifest = {
        "snapshot_schema_version": DATA_SNAPSHOT_SCHEMA_VERSION,
        "kind": DATA_SNAPSHOT_KIND,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "notes": notes or [],
        "panel": panel_payload,
        "references": {
            "raw_cache": raw_cache_payload,
            "factor_store": factor_store_payload,
        },
        "quality": _compact_quality_summary(
            panel=panel_quality_payload or {},
            raw_cache=raw_cache_payload,
        ),
        "checksums": checksums,
        "environment": {
            "cwd": str(Path.cwd()),
            "git": _git_metadata(Path.cwd()),
        },
    }

    manifest_path = output_path / "dataset_meta.json"
    checksums_path = output_path / "checksums.sha256"
    readme_path = output_path / "README.md"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_checksums(checksums_path, checksums)
    _write_readme(readme_path, manifest)
    return DataSnapshotResult(
        manifest_path=manifest_path,
        checksums_path=checksums_path,
        readme_path=readme_path,
        manifest=manifest,
    )
