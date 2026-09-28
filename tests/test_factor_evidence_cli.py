from __future__ import annotations

import json

import pandas as pd
import pytest

from moneytree.cli.factor_evidence import main
from moneytree.factors.publication import audit_public_snapshot


def _write_panel(path) -> None:
    pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"]
            ),
            "ticker": ["A", "B", "A", "B"],
            "alpha001": [1.0, 2.0, 2.0, 1.0],
            "next_period_return": [0.01, -0.01, 0.02, -0.02],
        }
    ).to_parquet(path)


def test_factor_evidence_cli_writes_public_json_snapshot(tmp_path, capsys) -> None:
    panel_path = tmp_path / "panel.parquet"
    output_path = tmp_path / "public" / "alpha810.json"
    _write_panel(panel_path)

    exit_code = main(
        [
            "--panel",
            str(panel_path),
            "--factors",
            "alpha001",
            "--data-version",
            "fixture-v1",
            "--output",
            str(output_path),
            "--format",
            "json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "moneytree_factor_evidence_snapshot"
    assert payload["data_version"] == "fixture-v1"
    assert '"kind": "moneytree_factor_evidence_snapshot"' in capsys.readouterr().out


def test_factor_evidence_cli_accepts_factor_file(tmp_path) -> None:
    panel_path = tmp_path / "panel.parquet"
    factor_file = tmp_path / "factors.txt"
    output_path = tmp_path / "alpha810.json"
    _write_panel(panel_path)
    factor_file.write_text("alpha001\n", encoding="utf-8")

    assert (
        main(
            [
                "--panel",
                str(panel_path),
                "--factors",
                str(factor_file),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    assert json.loads(output_path.read_text(encoding="utf-8"))["factors"][0]["name"] == "alpha001"


def test_factor_evidence_cli_returns_error_for_missing_panel(tmp_path, capsys) -> None:
    exit_code = main(
        [
            "--panel",
            str(tmp_path / "missing.parquet"),
            "--factors",
            "alpha001",
            "--output",
            str(tmp_path / "alpha810.json"),
        ]
    )

    assert exit_code == 1
    assert "Error:" in capsys.readouterr().err


def test_public_snapshot_audit_rejects_private_fields() -> None:
    with pytest.raises(ValueError, match="Forbidden public field"):
        audit_public_snapshot({"factors": [{"ticker": "A"}]})


def test_public_snapshot_audit_rejects_absolute_paths() -> None:
    with pytest.raises(ValueError, match="Absolute path"):
        audit_public_snapshot({"source": "/private/panel.parquet"})
