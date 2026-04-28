from __future__ import annotations

import pandas as pd
import pyarrow.parquet as pq
import pytest

from moneytree.cli.parquet_rewrite import build_parser, run_rewrite


def test_parquet_rewrite_cli_writes_zstd_output(tmp_path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-04", "2021-01-05"]),
            "ticker": ["000001.SZ", "000001.SZ"],
            "x": [1.0, 2.0],
        }
    ).to_parquet(input_path, index=False)

    args = build_parser().parse_args(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )
    result = run_rewrite(args)

    assert result.rows == 2
    assert result.columns == 3
    assert output_path.exists()
    assert pq.ParquetFile(output_path).metadata.row_group(0).column(0).compression == "ZSTD"


def test_parquet_rewrite_cli_applies_row_group_size(tmp_path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    pd.DataFrame({"x": [1.0, 2.0]}).to_parquet(input_path)

    args = build_parser().parse_args(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--row-group-size",
            "1",
        ]
    )
    result = run_rewrite(args)

    assert result.row_group_size == 1
    assert pq.ParquetFile(output_path).metadata.num_row_groups == 2


def test_parquet_rewrite_cli_refuses_in_place_rewrite(tmp_path) -> None:
    input_path = tmp_path / "input.parquet"
    pd.DataFrame({"x": [1.0]}).to_parquet(input_path)

    args = build_parser().parse_args(
        [
            "--input",
            str(input_path),
            "--output",
            str(input_path),
            "--overwrite",
        ]
    )

    with pytest.raises(ValueError, match="in-place"):
        run_rewrite(args)
