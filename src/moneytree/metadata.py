from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import pandas as pd

EXPERIMENT_MANIFEST_SCHEMA_VERSION = "1.0"
OUTPUT_SCHEMA_VERSION = "1.0"


def stable_json_dumps(value: Any) -> str:
    """Serialize metadata with deterministic ordering for hashing."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json_hash(value: Any) -> str:
    return sha256_text(stable_json_dumps(value))


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_metadata(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {
            "path": str(path),
            "exists": False,
            "size_bytes": None,
            "modified_at_utc": None,
            "sha256": None,
        }

    stat = file_path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": int(stat.st_size),
        "modified_at_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "sha256": sha256_file(file_path),
    }


def _index_schema(index: pd.Index) -> list[dict[str, str]]:
    if isinstance(index, pd.MultiIndex):
        return [
            {
                "name": str(name) if name is not None else "",
                "dtype": str(index.get_level_values(level).dtype),
            }
            for level, name in enumerate(index.names)
        ]
    return [
        {
            "name": str(index.name) if index.name is not None else "",
            "dtype": str(index.dtype),
        }
    ]


def dataframe_schema(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "index": _index_schema(frame.index),
        "columns": [
            {
                "name": str(column),
                "dtype": str(dtype),
            }
            for column, dtype in frame.dtypes.items()
        ],
    }


def dataframe_schema_hash(frame: pd.DataFrame) -> str:
    return stable_json_hash(dataframe_schema(frame))


def dataframe_content_hash(frame: pd.DataFrame) -> str:
    """Hash DataFrame schema and values without depending on parquet bytes."""
    digest = hashlib.sha256()
    digest.update(stable_json_dumps(dataframe_schema(frame)).encode("utf-8"))
    row_hashes = pd.util.hash_pandas_object(frame, index=True).to_numpy(dtype="uint64")
    digest.update(row_hashes.tobytes())
    return digest.hexdigest()


def _date_range_summary(frame: pd.DataFrame) -> dict[str, str | None]:
    values: pd.Index | pd.Series | None = None
    if isinstance(frame.index, pd.MultiIndex) and "date" in frame.index.names:
        values = frame.index.get_level_values("date")
    elif frame.index.name == "date":
        values = frame.index
    elif "date" in frame.columns:
        values = frame["date"]

    if values is None:
        return {"min": None, "max": None}

    parsed = pd.to_datetime(values, errors="coerce")
    if len(parsed) == 0 or pd.isna(parsed).all():
        return {"min": None, "max": None}
    return {
        "min": pd.Timestamp(parsed.min()).isoformat(),
        "max": pd.Timestamp(parsed.max()).isoformat(),
    }


def _ticker_count(frame: pd.DataFrame) -> int | None:
    if isinstance(frame.index, pd.MultiIndex) and "ticker" in frame.index.names:
        return int(frame.index.get_level_values("ticker").nunique())
    if frame.index.name == "ticker":
        return int(frame.index.nunique())
    if "ticker" in frame.columns:
        return int(frame["ticker"].nunique())
    return None


def dataframe_metadata(frame: pd.DataFrame) -> dict[str, Any]:
    schema = dataframe_schema(frame)
    return {
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "date_range": _date_range_summary(frame),
        "ticker_count": _ticker_count(frame),
        "schema": schema,
        "schema_hash": stable_json_hash(schema),
    }


def config_metadata(config_paths: list[str | Path], resolved_config: dict[str, Any]) -> dict[str, Any]:
    files = [file_metadata(path) for path in config_paths]
    file_hash_inputs = [
        {
            "path": item["path"],
            "sha256": item["sha256"],
        }
        for item in files
    ]
    return {
        "files": files,
        "files_hash": stable_json_hash(file_hash_inputs),
        "resolved_config_hash": stable_json_hash(resolved_config),
    }


def _package_version(name: str) -> str | None:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None


def runtime_metadata() -> dict[str, Any]:
    packages = [
        "money-trees",
        "numpy",
        "pandas",
        "scikit-learn",
        "scipy",
        "pyarrow",
        "PyYAML",
        "optuna",
        "matplotlib",
        "xgboost",
        "tushare",
    ]
    return {
        "python": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": {name: _package_version(name) for name in packages},
    }


def dataset_version(input_sha256: str | None, schema_hash: str) -> str:
    input_part = input_sha256[:12] if input_sha256 else "noinputhash"
    return f"input-{input_part}-schema-{schema_hash[:12]}"


def build_experiment_manifest(
    *,
    settings,
    raw_frame: pd.DataFrame,
    model_frame: pd.DataFrame,
    model_id: str,
    model_target_column: str,
    output_dir: str | Path,
    git_commit: str | None,
    resolved_at_utc: str,
) -> dict[str, Any]:
    input_data = file_metadata(settings.data)
    raw_input = dataframe_metadata(raw_frame)
    model_input = dataframe_metadata(model_frame)
    config = config_metadata(settings.config_paths, settings.resolved_config)
    version = dataset_version(input_data["sha256"], raw_input["schema_hash"])

    return {
        "manifest_schema_version": EXPERIMENT_MANIFEST_SCHEMA_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "run": {
            "resolved_at_utc": resolved_at_utc,
            "git_commit": git_commit,
            "random_seed": int(settings.random_seed),
            "output_dir": str(output_dir),
        },
        "dataset": {
            "dataset_version": version,
            "basis": "input_file_sha256+raw_input_schema_hash",
        },
        "input_data": input_data,
        "schemas": {
            "raw_input": raw_input,
            "model_frame": model_input,
        },
        "config": config,
        "model": {
            "id": model_id,
            "target_column": model_target_column,
            "params": dict(settings.model_params),
        },
        "market": {
            "profile": settings.market_profile,
            "benchmark": settings.benchmark_name,
            "benchmark_return_column": settings.benchmark_return_column,
            "benchmark_cum_column": settings.benchmark_cum_column,
            "label_source": settings.label_source,
            "label_threshold": float(settings.label_threshold),
            "feature_lag_periods": int(settings.feature_lag_periods),
        },
        "runtime": runtime_metadata(),
    }
