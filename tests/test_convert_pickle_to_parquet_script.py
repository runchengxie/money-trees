from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_convert_pickle_to_parquet_script_smoke(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    input_path = tmp_path / "sample.pkl"
    output_path = tmp_path / "sample.parquet"

    frame = pd.DataFrame(
        {
            "date": ["2021-03-31", "2021-03-31"],
            "ticker": ["AAA", "BBB"],
            "f1": [1.0, 2.0],
            "next_period_return": [0.01, -0.02],
            "benchmark_next_period_return": [0.0, 0.0],
            "benchmark_cum_ret": [100.0, 100.0],
        }
    )
    frame.to_pickle(input_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/convert_pickle_to_parquet.py",
            "--input",
            str(input_path),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert output_path.exists()
    out = pd.read_parquet(output_path)
    assert len(out) == len(frame)
    assert list(out.columns) == list(frame.columns)
    assert "Compatibility notice:" in result.stdout
    assert "moneytrees-parquet-rewrite" in result.stdout
    assert "Rows:" in result.stdout
    assert "Columns:" in result.stdout
