from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
from typing import Any

from moneytree.data import load_market_data
from moneytree.data_quality import build_parquet_panel_quality_payload
from moneytree.data_quality import build_tushare_panel_quality_result


@dataclass(frozen=True)
class DataStatusReport:
    layers: dict[str, dict[str, Any]]

    @property
    def errors(self) -> list[str]:
        found: list[str] = []
        for name, layer in self.layers.items():
            for error in layer.get("errors", []):
                found.append(f"{name}: {error}")
        return found

    @property
    def warnings(self) -> list[str]:
        found: list[str] = []
        for name, layer in self.layers.items():
            for warning in layer.get("warnings", []):
                found.append(f"{name}: {warning}")
        return found

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.ok else "error",
            "layers": self.layers,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def to_lines(self) -> list[str]:
        status = "ok" if self.ok else "error"
        lines = [f"[data-status] status={status} layers={','.join(self.layers)}"]
        for name, layer in self.layers.items():
            lines.extend(_layer_lines(name, layer))
        return lines


def _path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def _base_layer(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {
            "status": "error",
            "path": str(file_path),
            "exists": False,
            "errors": [f"panel path does not exist: {file_path}"],
            "warnings": [],
        }

    try:
        if file_path.suffix.lower() == ".parquet":
            return build_parquet_panel_quality_payload(file_path)
        frame = load_market_data(file_path)
        quality = build_tushare_panel_quality_result(frame)
    except Exception as exc:
        return {
            "status": "error",
            "path": str(file_path),
            "exists": True,
            "file_size": file_path.stat().st_size if file_path.is_file() else None,
            "errors": [str(exc)],
            "warnings": [],
        }

    payload = quality.to_dict()
    return {
        "status": "ok" if quality.ok else "error",
        "path": str(file_path),
        "exists": True,
        "file_size": file_path.stat().st_size,
        "rows": payload["row_count"],
        "columns": payload["column_count"],
        "date_min": payload["date_min"],
        "date_max": payload["date_max"],
        "date_count": payload["date_count"],
        "ticker_count": payload["ticker_count"],
        "duplicate_key_count": payload["duplicate_key_count"],
        "missing_required_columns": payload["missing_required_columns"],
        "null_rates": payload["null_rates"],
        "null_counts": {
            key: int(float(value) * len(frame))
            for key, value in payload["null_rates"].items()
        },
        "non_positive_price_counts": payload["non_positive_price_counts"],
        "negative_volume_count": payload["negative_volume_count"],
        "inverted_ohlc_count": payload["inverted_ohlc_count"],
        "errors": payload["errors"],
        "warnings": payload["warnings"],
    }


def _raw_cache_manifest_path(path: str | Path) -> Path:
    cache_path = Path(path)
    if cache_path.is_dir():
        return cache_path / "manifest.sqlite"
    return cache_path


def _raw_cache_layer(path: str | Path) -> dict[str, Any]:
    manifest_path = _raw_cache_manifest_path(path)
    if not manifest_path.exists():
        return {
            "status": "error",
            "path": str(path),
            "manifest_path": str(manifest_path),
            "manifest_exists": False,
            "apis": {},
            "errors": [f"raw cache manifest does not exist: {manifest_path}"],
            "warnings": [],
        }

    try:
        with sqlite3.connect(manifest_path) as conn:
            rows = conn.execute(
                """
                SELECT source, api_name, min(trade_date), max(trade_date),
                       count(*), coalesce(sum(rows), 0),
                       count(DISTINCT schema_hash), count(DISTINCT content_hash)
                FROM raw_cache
                GROUP BY source, api_name
                ORDER BY source, api_name
                """
            ).fetchall()
            date_rows = conn.execute(
                """
                SELECT source, api_name, trade_date, rows
                FROM raw_cache
                WHERE source = 'tushare'
                  AND api_name IN ('daily', 'adj_factor', 'daily_basic')
                ORDER BY trade_date, api_name
                """
            ).fetchall()
    except Exception as exc:
        return {
            "status": "error",
            "path": str(path),
            "manifest_path": str(manifest_path),
            "manifest_exists": True,
            "apis": {},
            "errors": [str(exc)],
            "warnings": [],
        }

    apis: dict[str, dict[str, Any]] = {}
    for (
        source,
        api_name,
        date_min,
        date_max,
        shard_count,
        row_count,
        schema_hash_count,
        content_hash_count,
    ) in rows:
        key = f"{source}.{api_name}"
        apis[key] = {
            "source": source,
            "api_name": api_name,
            "date_min": date_min,
            "date_max": date_max,
            "shards": int(shard_count),
            "rows": int(row_count),
            "schema_hash_count": int(schema_hash_count),
            "content_hash_count": int(content_hash_count),
        }

    errors: list[str] = []
    warnings: list[str] = []
    if not apis:
        errors.append("raw cache manifest has no raw_cache entries")
    for api_name, api in apis.items():
        if int(api.get("schema_hash_count", 0)) > 1:
            warnings.append(
                f"{api_name} has {api.get('schema_hash_count')} distinct schema hashes"
            )
    by_date: dict[str, dict[str, int]] = {}
    for source, api_name, trade_date, row_count in date_rows:
        if source != "tushare":
            continue
        by_date.setdefault(str(trade_date), {})[str(api_name)] = int(row_count)
    raw_anomalies: list[dict[str, Any]] = []
    for trade_date, counts in sorted(by_date.items()):
        daily_rows = int(counts.get("daily", 0))
        if daily_rows <= 0:
            continue
        for related in ("adj_factor", "daily_basic"):
            related_rows = counts.get(related)
            if related_rows is None:
                message = (
                    f"tushare.{related} missing shard for trade_date={trade_date} "
                    f"while tushare.daily rows={daily_rows}"
                )
            elif int(related_rows) == 0:
                message = (
                    f"tushare.{related} has zero rows for trade_date={trade_date} "
                    f"while tushare.daily rows={daily_rows}"
                )
            else:
                continue
            raw_anomalies.append(
                {
                    "api_name": related,
                    "trade_date": trade_date,
                    "daily_rows": daily_rows,
                    "rows": related_rows,
                    "message": message,
                }
            )
            errors.append(message)
    return {
        "status": "ok" if not errors else "error",
        "path": str(path),
        "manifest_path": str(manifest_path),
        "manifest_exists": True,
        "apis": apis,
        "anomalies": raw_anomalies,
        "errors": errors,
        "warnings": warnings,
    }


def _factor_store_manifest_path(path: str | Path) -> Path:
    store_path = Path(path)
    if store_path.is_dir():
        return store_path / "manifest.json"
    return store_path


def _factor_store_layer(path: str | Path) -> dict[str, Any]:
    manifest_path = _factor_store_manifest_path(path)
    if not manifest_path.exists():
        return {
            "status": "error",
            "path": str(path),
            "manifest_path": str(manifest_path),
            "manifest_exists": False,
            "errors": [f"factor-store manifest does not exist: {manifest_path}"],
            "warnings": [],
            "factor_families": {},
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "error",
            "path": str(path),
            "manifest_path": str(manifest_path),
            "manifest_exists": True,
            "errors": [str(exc)],
            "warnings": [],
            "factor_families": {},
        }

    root = manifest_path.parent
    errors: list[str] = []
    base_panel = dict(manifest.get("base_panel", {}))
    base_path_text = base_panel.get("path")
    if not base_path_text:
        errors.append("factor-store manifest is missing base_panel.path")
    else:
        base_path = root / str(base_path_text)
        if not base_path.exists():
            errors.append(f"base panel file does not exist: {base_path}")

    families: dict[str, dict[str, Any]] = {}
    raw_families = manifest.get("factor_families", {})
    if not isinstance(raw_families, dict):
        errors.append("factor-store manifest factor_families must be an object")
        raw_families = {}
    for family, entry in raw_families.items():
        if not isinstance(entry, dict):
            errors.append(f"{family} factor entry must be an object")
            continue
        raw_paths = entry.get("paths")
        paths = list(raw_paths) if isinstance(raw_paths, list) else []
        if not paths and entry.get("path"):
            paths = [str(entry["path"])]
        missing_paths = [path for path in paths if not (root / str(path)).exists()]
        for missing in missing_paths:
            errors.append(f"{family} factor file does not exist: {root / str(missing)}")
        families[str(family)] = {
            "prefix": entry.get("prefix"),
            "rows": entry.get("rows"),
            "columns": entry.get("columns"),
            "partitioned": bool(entry.get("partitioned") or raw_paths),
            "partitions": len(paths),
            "paths": paths,
            "missing_paths": missing_paths,
            "chunk_trade_dates": entry.get("chunk_trade_dates"),
        }

    return {
        "status": "ok" if not errors else "error",
        "path": str(path),
        "manifest_path": str(manifest_path),
        "manifest_exists": True,
        "manifest_schema_version": manifest.get("manifest_schema_version"),
        "kind": manifest.get("kind"),
        "base_panel": base_panel,
        "factor_families": families,
        "factor_dtype": manifest.get("factor_dtype"),
        "compression": manifest.get("compression"),
        "compression_level": manifest.get("compression_level"),
        "row_group_size": manifest.get("row_group_size"),
        "key_validation": manifest.get("key_validation", {}),
        "errors": errors,
        "warnings": [],
    }


def _artifact_layer(path: str | Path) -> dict[str, Any]:
    artifact_path = Path(path)
    if not artifact_path.exists():
        return {
            "status": "error",
            "path": str(artifact_path),
            "exists": False,
            "errors": [f"artifact path does not exist: {artifact_path}"],
            "warnings": [],
            "known_files": {},
            "total_size": 0,
        }

    known_names = (
        "experiment_manifest.json",
        "metrics.json",
        "metrics.csv",
        "run_config.yaml",
        "run_config.json",
        "predictions.parquet",
        "preprocessed.parquet",
    )
    known_files = {
        name: {
            "exists": (artifact_path / name).exists(),
            "size": (artifact_path / name).stat().st_size if (artifact_path / name).exists() else 0,
        }
        for name in known_names
    }
    return {
        "status": "ok",
        "path": str(artifact_path),
        "exists": True,
        "known_files": known_files,
        "total_size": _path_size(artifact_path),
        "errors": [],
        "warnings": [],
    }


def build_data_status_report(
    *,
    panel: str | Path | None = None,
    raw_cache: str | Path | None = None,
    factor_store: str | Path | None = None,
    artifacts: str | Path | None = None,
) -> DataStatusReport:
    layers: dict[str, dict[str, Any]] = {}
    if panel is not None:
        layers["base_panel"] = _base_layer(panel)
    if raw_cache is not None:
        layers["raw_cache"] = _raw_cache_layer(raw_cache)
    if factor_store is not None:
        layers["factor_store"] = _factor_store_layer(factor_store)
    if artifacts is not None:
        layers["artifacts"] = _artifact_layer(artifacts)
    if not layers:
        raise ValueError("At least one data layer path is required.")
    return DataStatusReport(layers=layers)


def _layer_lines(name: str, layer: dict[str, Any]) -> list[str]:
    status = layer.get("status", "unknown")
    path = layer.get("path") or layer.get("manifest_path") or "NA"
    lines = [f"[data-status:{name}] status={status} path={path}"]
    if name == "base_panel":
        lines.append(
            (
                f"[data-status:{name}] rows={layer.get('rows', 'NA')} "
                f"cols={layer.get('columns', 'NA')} dates={layer.get('date_count', 'NA')} "
                f"tickers={layer.get('ticker_count', 'NA')} "
                f"start={layer.get('date_min') or 'NA'} end={layer.get('date_max') or 'NA'} "
                f"duplicate_keys={layer.get('duplicate_key_count', 'NA')}"
            )
        )
        if layer.get("out_of_order_count", 0):
            lines.append(
                f"[data-status:{name}] out_of_order={layer.get('out_of_order_count', 0)} "
                f"duplicate_check_exact={layer.get('duplicate_check_exact')}"
            )
        derived = layer.get("derived_return_checks", {})
        if derived.get("checked"):
            rendered = []
            for column in (
                "return_1d",
                "next_period_return",
                "benchmark_return",
                "benchmark_next_period_return",
            ):
                check = derived.get(column)
                if isinstance(check, dict):
                    rendered.append(
                        f"{column}:mismatch={check.get('mismatch_count', 0)},"
                        f"unexpected_null={check.get('unexpected_null_count', 0)}"
                    )
            if rendered:
                lines.append(f"[data-status:{name}] derived_returns {'; '.join(rendered)}")
        adjusted = layer.get("adjusted_price_checks", {})
        if adjusted.get("checked"):
            mismatch_counts = adjusted.get("mismatch_counts", {})
            null_counts = adjusted.get("null_counts", {})
            lines.append(
                f"[data-status:{name}] adjusted_prices "
                f"nulls={json.dumps(null_counts, sort_keys=True)} "
                f"mismatches={json.dumps(mismatch_counts, sort_keys=True)}"
            )
    elif name == "raw_cache":
        for api_name, api in layer.get("apis", {}).items():
            lines.append(
                (
                    f"[data-status:{name}] api={api_name} "
                    f"start={api.get('date_min') or 'NA'} end={api.get('date_max') or 'NA'} "
                    f"shards={api.get('shards', 0)} rows={api.get('rows', 0)} "
                    f"schema_hashes={api.get('schema_hash_count', 0)}"
                )
            )
        for anomaly in layer.get("anomalies", []):
            lines.append(
                f"[data-status:{name}] anomaly api=tushare.{anomaly.get('api_name')} "
                f"trade_date={anomaly.get('trade_date')} rows={anomaly.get('rows')} "
                f"daily_rows={anomaly.get('daily_rows')}"
            )
    elif name == "factor_store":
        base = layer.get("base_panel", {})
        lines.append(
            (
                f"[data-status:{name}] base_rows={base.get('rows', 'NA')} "
                f"base_cols={base.get('columns', 'NA')} "
                f"families={','.join(layer.get('factor_families', {}))}"
            )
        )
        for family, entry in layer.get("factor_families", {}).items():
            lines.append(
                (
                    f"[data-status:{name}] family={family} prefix={entry.get('prefix') or 'NA'} "
                    f"rows={entry.get('rows', 'NA')} cols={entry.get('columns', 'NA')} "
                    f"partitions={entry.get('partitions', 0)}"
                )
            )
    elif name == "artifacts":
        lines.append(f"[data-status:{name}] total_size={layer.get('total_size', 0)}")

    for warning in layer.get("warnings", []):
        lines.append(f"[data-status:{name}] warning {warning}")
    for error in layer.get("errors", []):
        lines.append(f"[data-status:{name}] error {error}")
    return lines
