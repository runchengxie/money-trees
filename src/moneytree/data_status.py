from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
import numpy as np
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


def _factor_store_family_quality(
    root: Path,
    entry: dict[str, Any],
    *,
    family: str,
    max_null_rate: float = 0.95,
    batch_size: int = 250_000,
) -> dict[str, Any]:
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - pyarrow is a core dependency
        raise RuntimeError("Factor-store quality checks require pyarrow.") from exc

    raw_paths = entry.get("paths")
    paths = list(raw_paths) if isinstance(raw_paths, list) else []
    if not paths and entry.get("path"):
        paths = [str(entry["path"])]
    prefix = str(entry.get("prefix") or f"{family}_")
    expected_columns = entry.get("columns")
    expected_rows = entry.get("rows")

    rows_checked = 0
    partitions_checked = 0
    row_mismatch_count = 0
    duplicate_key_count = 0
    factor_columns: list[str] = []
    column_stats: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    warnings: list[str] = []

    for raw_path in paths:
        part_path = root / str(raw_path)
        if not part_path.exists():
            continue
        parquet_file = pq.ParquetFile(part_path)
        schema_names = [str(name) for name in parquet_file.schema_arrow.names]
        part_factor_columns = [name for name in schema_names if name.startswith(prefix)]
        if not part_factor_columns:
            errors.append(f"{family} factor file has no columns with prefix {prefix}: {raw_path}")
            continue
        if not factor_columns:
            factor_columns = part_factor_columns
            column_stats = {
                column: {
                    "nan_count": 0,
                    "inf_count": 0,
                    "finite_count": 0,
                    "min": math.inf,
                    "max": -math.inf,
                }
                for column in factor_columns
            }
        elif part_factor_columns != factor_columns:
            errors.append(f"{family} factor schema differs in {raw_path}")

        part_rows = int(parquet_file.metadata.num_rows)
        rows_checked += part_rows
        partitions_checked += 1

        part_meta = None
        for candidate in entry.get("parts", []):
            if isinstance(candidate, dict) and str(candidate.get("path")) == str(raw_path):
                part_meta = candidate
                break
        if part_meta is not None and int(part_meta.get("rows", part_rows)) != part_rows:
            row_mismatch_count += 1

        scan_columns = [
            column
            for column in ("date", "ticker", *part_factor_columns)
            if column in schema_names
        ]
        if "date" not in scan_columns or "ticker" not in scan_columns:
            errors.append(f"{family} factor file missing date/ticker keys: {raw_path}")

        for batch in parquet_file.iter_batches(columns=scan_columns, batch_size=batch_size):
            names = batch.schema.names
            if "date" in names and "ticker" in names:
                keys = batch.select(["date", "ticker"]).to_pandas(ignore_metadata=True)
                duplicate_key_count += int(keys.duplicated(["date", "ticker"]).sum())

            for column in part_factor_columns:
                if column not in names or column not in column_stats:
                    continue
                values = batch.column(names.index(column)).to_numpy(zero_copy_only=False)
                numeric = np.asarray(values, dtype="float64")
                nan_mask = np.isnan(numeric)
                inf_mask = np.isinf(numeric)
                finite_mask = np.isfinite(numeric)
                stats = column_stats[column]
                stats["nan_count"] += int(nan_mask.sum())
                stats["inf_count"] += int(inf_mask.sum())
                finite_count = int(finite_mask.sum())
                stats["finite_count"] += finite_count
                if finite_count:
                    finite_values = numeric[finite_mask]
                    stats["min"] = min(float(stats["min"]), float(finite_values.min()))
                    stats["max"] = max(float(stats["max"]), float(finite_values.max()))

    observed_columns = len(factor_columns)
    if expected_columns is not None and observed_columns != int(expected_columns):
        errors.append(
            f"{family} observed factor columns {observed_columns} != manifest columns {expected_columns}"
        )
    if expected_rows is not None and rows_checked != int(expected_rows):
        errors.append(f"{family} observed rows {rows_checked} != manifest rows {expected_rows}")
    if row_mismatch_count:
        errors.append(f"{family} has {row_mismatch_count} partitions with row-count metadata mismatch")
    if duplicate_key_count:
        errors.append(f"{family} has duplicate date/ticker keys: {duplicate_key_count}")

    total_nan = int(sum(stats["nan_count"] for stats in column_stats.values()))
    total_inf = int(sum(stats["inf_count"] for stats in column_stats.values()))
    all_null_columns = [
        column
        for column, stats in column_stats.items()
        if rows_checked > 0 and int(stats["finite_count"]) == 0 and int(stats["inf_count"]) == 0
    ]
    constant_columns = [
        column
        for column, stats in column_stats.items()
        if int(stats["finite_count"]) == rows_checked
        and math.isfinite(float(stats["min"]))
        and math.isfinite(float(stats["max"]))
        and float(stats["min"]) == float(stats["max"])
    ]
    high_null_rate_columns = []
    for column, stats in column_stats.items():
        null_rate = float(stats["nan_count"]) / float(rows_checked) if rows_checked else 0.0
        if null_rate > float(max_null_rate):
            high_null_rate_columns.append(
                {
                    "column": column,
                    "null_rate": null_rate,
                    "nan_count": int(stats["nan_count"]),
                }
            )
    high_null_rate_columns.sort(key=lambda item: item["null_rate"], reverse=True)
    max_null_rate_observed = (
        max((float(stats["nan_count"]) / float(rows_checked) for stats in column_stats.values()), default=0.0)
        if rows_checked
        else 0.0
    )

    if total_inf:
        errors.append(f"{family} has {total_inf} infinite factor values")
    if all_null_columns:
        errors.append(f"{family} has {len(all_null_columns)} all-null factor columns")
    if high_null_rate_columns:
        warnings.append(
            f"{family} has {len(high_null_rate_columns)} factor columns with null_rate > {max_null_rate:.2f}"
        )
    if constant_columns:
        warnings.append(f"{family} has {len(constant_columns)} constant factor columns")

    return {
        "checked": True,
        "rows_checked": rows_checked,
        "partitions_checked": partitions_checked,
        "columns_checked": observed_columns,
        "nan_count": total_nan,
        "inf_count": total_inf,
        "max_null_rate": max_null_rate_observed,
        "high_null_rate_columns": high_null_rate_columns[:10],
        "all_null_column_count": len(all_null_columns),
        "all_null_columns": all_null_columns[:20],
        "constant_column_count": len(constant_columns),
        "constant_columns": constant_columns[:20],
        "duplicate_key_count": duplicate_key_count,
        "row_mismatch_count": row_mismatch_count,
        "errors": errors,
        "warnings": warnings,
    }


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
    warnings: list[str] = []
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
        quality = (
            _factor_store_family_quality(root, entry, family=str(family))
            if not missing_paths
            else {"checked": False, "errors": [], "warnings": []}
        )
        errors.extend(str(error) for error in quality.get("errors", []))
        warnings.extend(str(warning) for warning in quality.get("warnings", []))
        families[str(family)] = {
            "prefix": entry.get("prefix"),
            "rows": entry.get("rows"),
            "columns": entry.get("columns"),
            "partitioned": bool(entry.get("partitioned") or raw_paths),
            "partitions": len(paths),
            "paths": paths,
            "missing_paths": missing_paths,
            "chunk_trade_dates": entry.get("chunk_trade_dates"),
            "quality": quality,
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
        "warnings": warnings,
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
            quality = entry.get("quality", {})
            if quality.get("checked"):
                lines.append(
                    (
                        f"[data-status:{name}] family={family} quality "
                        f"rows_checked={quality.get('rows_checked', 0)} "
                        f"cols_checked={quality.get('columns_checked', 0)} "
                        f"nan={quality.get('nan_count', 0)} "
                        f"inf={quality.get('inf_count', 0)} "
                        f"max_null_rate={float(quality.get('max_null_rate', 0.0)):.4f} "
                        f"all_null_cols={quality.get('all_null_column_count', 0)} "
                        f"constant_cols={quality.get('constant_column_count', 0)} "
                        f"duplicate_keys={quality.get('duplicate_key_count', 0)}"
                    )
                )
    elif name == "artifacts":
        lines.append(f"[data-status:{name}] total_size={layer.get('total_size', 0)}")

    for warning in layer.get("warnings", []):
        lines.append(f"[data-status:{name}] warning {warning}")
    for error in layer.get("errors", []):
        lines.append(f"[data-status:{name}] error {error}")
    return lines
