from __future__ import annotations

import pandas as pd
import pytest

from moneytree.resources import (
    ResourcePreflightError,
    available_memory_bytes,
    ensure_memory_available,
    estimate_parquet_dataframe_memory,
    format_bytes,
)


def test_available_memory_bytes_reads_meminfo(tmp_path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:       8000000 kB\nMemAvailable:   1234567 kB\n",
        encoding="utf-8",
    )

    assert available_memory_bytes(meminfo) == 1_234_567 * 1024


def test_estimate_parquet_dataframe_memory_uses_metadata(tmp_path) -> None:
    path = tmp_path / "panel.parquet"
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-01", "2021-01-02"]),
            "ticker": ["A", "B"],
            "alpha101_001": [1.0, 2.0],
        }
    ).to_parquet(path, index=False)

    estimate = estimate_parquet_dataframe_memory(path)

    assert estimate is not None
    assert estimate.rows == 2
    assert estimate.columns == 3
    assert estimate.file_size_bytes > 0
    assert estimate.required_bytes >= estimate.file_size_bytes


def test_ensure_memory_available_reports_context() -> None:
    with pytest.raises(ResourcePreflightError, match="demo"):
        ensure_memory_available(
            required_bytes=200,
            available_bytes=100,
            budget_fraction=1.0,
            context="demo",
            detail="rows=2",
            remediation="reduce input",
        )


def test_format_bytes() -> None:
    assert format_bytes(None) == "unknown"
    assert format_bytes(1024) == "1.0KiB"
