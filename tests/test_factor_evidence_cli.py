from __future__ import annotations

import io
import json
import tarfile

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


def _write_factor_store_archive(path) -> None:
    index = pd.MultiIndex.from_product(
        [pd.to_datetime(["2016-01-04", "2016-01-05"]), ["A", "B"]],
        names=["date", "ticker"],
    )
    base = pd.DataFrame({"next_period_return": [0.01, -0.01, 0.02, -0.02]}, index=index)
    factors = pd.DataFrame({"alpha101_001": [1.0, 2.0, 2.0, 1.0]}, index=index)
    base_buffer = io.BytesIO()
    factor_buffer = io.BytesIO()
    base.to_parquet(base_buffer)
    factors.to_parquet(factor_buffer)
    prefix = "data/factor_store/cn_daily_2016_2025"
    manifest = {
        "manifest_schema_version": "1.0",
        "kind": "moneytree_factor_store",
        "base_panel": {"path": "base.parquet", "rows": 4, "columns": 1},
        "factor_families": {
            "alpha101": {
                "paths": ["factors/alpha101/part-0001.parquet"],
                "parts": [{
                    "path": "factors/alpha101/part-0001.parquet",
                    "start_date": "2016-01-04",
                    "end_date": "2016-01-05",
                    "rows": 4,
                }],
            }
        },
    }
    with tarfile.open(path, "w") as archive:
        for name, data in [
            (f"{prefix}/manifest.json", json.dumps(manifest).encode()),
            (f"{prefix}/base.parquet", base_buffer.getvalue()),
            (f"{prefix}/factors/alpha101/part-0001.parquet", factor_buffer.getvalue()),
        ]:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))


def test_factor_evidence_cli_writes_public_json_snapshot(tmp_path, capsys) -> None:
    panel_path = tmp_path / "panel.parquet"
    output_path = tmp_path / "public" / "alpha810.json"
    evidence_path = tmp_path / "public" / "factor_evidence.v1.json"
    _write_panel(panel_path)

    exit_code = main(
        [
            "--panel",
            str(panel_path),
            "--factors",
            "alpha001",
            "--data-version",
            "fixture-v1",
            "--code-revision",
            "abc1234",
            "--output",
            str(output_path),
            "--evidence-v1-output",
            str(evidence_path),
            "--format",
            "json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "moneytree_factor_evidence_snapshot"
    assert payload["data_version"] == "fixture-v1"
    assert payload["code_revision"] == "abc1234"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["provenance"]["code_revision"] == "abc1234"
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


def test_factor_evidence_cli_uses_explicit_holding_period(tmp_path) -> None:
    panel_path = tmp_path / "panel.parquet"
    output_path = tmp_path / "alpha810.json"
    _write_panel(panel_path)

    assert main(
        [
            "--panel",
            str(panel_path),
            "--factors",
            "alpha001",
            "--holding-period-days",
            "1",
            "--output",
            str(output_path),
        ]
    ) == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["uncertainty"]["status"] == "complete"
    assert payload["uncertainty"]["holding_period_days"] == 1


def test_factor_evidence_cli_accepts_unextracted_factor_store_archive(tmp_path) -> None:
    archive_path = tmp_path / "factor-store.tar"
    output_path = tmp_path / "alpha810.json"
    _write_factor_store_archive(archive_path)

    assert (
        main(
            [
                "--factor-store-archive",
                str(archive_path),
                "--factors",
                "all",
                "--data-version",
                "archive-fixture-v1",
                "--code-revision",
                "archive123",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["data_version"] == "archive-fixture-v1"
    assert payload["code_revision"] == "archive123"
    assert payload["factors"][0]["name"] == "alpha101_001"


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
