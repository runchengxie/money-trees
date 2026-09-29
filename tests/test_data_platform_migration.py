from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_primary_data_path_points_to_market_data_platform() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    migration = (ROOT / "docs/data-platform-migration.md").read_text(encoding="utf-8")

    assert "quant-market-data-platform" in readme
    assert "marketdata" in migration
    assert "moneytrees-tushare" in migration
    assert "deprecated" in migration


def test_tushare_cli_is_marked_as_compatibility_path() -> None:
    cli = (ROOT / "docs/cli-reference.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs/runbook.md").read_text(encoding="utf-8")

    assert "compatibility" in cli
    assert "quant-market-data-platform" in cli
    assert "quant-market-data-platform" in runbook
