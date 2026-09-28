from __future__ import annotations

import json
import subprocess
import sys

import pandas as pd


def test_synthetic_public_factor_release_contains_no_private_rows(tmp_path) -> None:
    panel_path = tmp_path / "private-panel.parquet"
    output_path = tmp_path / "public" / "alpha810-snapshot.json"
    pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"]
            ),
            "ticker": ["A", "B", "A", "B"],
            "alpha001": [1.0, 2.0, 2.0, 1.0],
            "next_period_return": [0.01, -0.01, 0.02, -0.02],
        }
    ).to_parquet(panel_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_public_factor_snapshot.py",
            "--panel",
            str(panel_path),
            "--factors",
            "alpha001",
            "--data-version",
            "fixture-v1",
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "moneytree_factor_evidence_snapshot"
    assert payload["data_version"] == "fixture-v1"
    assert '"ticker"' not in json.dumps(payload)
    assert "private-panel.parquet" not in json.dumps(payload)
