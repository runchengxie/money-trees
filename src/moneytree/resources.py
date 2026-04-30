from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParquetMemoryEstimate:
    rows: int
    columns: int
    file_size_bytes: int
    required_bytes: int


class ResourcePreflightError(RuntimeError):
    """Raised when a resource preflight predicts an avoidable failure."""


def format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024.0 or unit == "TiB":
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}TiB"


def available_memory_bytes(meminfo_path: str | Path = "/proc/meminfo") -> int | None:
    try:
        for line in Path(meminfo_path).read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1]) * 1024
    except OSError:
        return None
    return None


def estimate_parquet_dataframe_memory(
    path: str | Path,
    *,
    file_size_multiplier: int = 6,
    per_cell_bytes: int = 16,
) -> ParquetMemoryEstimate | None:
    file_path = Path(path)
    if file_path.suffix.lower() != ".parquet" or not file_path.exists():
        return None
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError:
        return None

    parquet_file = pq.ParquetFile(file_path)
    rows = int(parquet_file.metadata.num_rows)
    columns = len(parquet_file.schema_arrow.names)
    file_size = int(file_path.stat().st_size)
    required = max(
        file_size * int(file_size_multiplier),
        rows * max(columns, 1) * int(per_cell_bytes),
    )
    return ParquetMemoryEstimate(
        rows=rows,
        columns=columns,
        file_size_bytes=file_size,
        required_bytes=int(required),
    )


def ensure_memory_available(
    *,
    required_bytes: int,
    available_bytes: int | None,
    budget_fraction: float = 0.85,
    context: str,
    detail: str,
    remediation: str,
) -> None:
    if available_bytes is None:
        return
    usable = int(available_bytes * float(budget_fraction))
    if int(required_bytes) <= usable:
        return
    raise ResourcePreflightError(
        f"{context}: {detail}, estimated_required={format_bytes(int(required_bytes))}, "
        f"available={format_bytes(available_bytes)}. {remediation}"
    )
