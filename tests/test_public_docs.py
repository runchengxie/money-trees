from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_mkdocs_navigation_references_existing_public_docs() -> None:
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))

    assert config["site_name"] == "Money Trees · Alpha 810 Research"
    nav_paths = [item for section in config["nav"] for item in section.values()]
    for path in nav_paths:
        assert (ROOT / "docs" / path).exists(), path


def test_readme_links_to_public_evidence_guide() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "public-factor-evidence.md" in readme
    assert "quant-platform" in readme
    assert "quant-backtest-runtime" in readme


def test_docs_workflow_builds_strict_mkdocs_site() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-docs.yml").read_text(
        encoding="utf-8"
    )

    assert "mkdocs build --strict" in workflow
    assert "actions/upload-pages-artifact" in workflow
    assert "actions/deploy-pages" in workflow
