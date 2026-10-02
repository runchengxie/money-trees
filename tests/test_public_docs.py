from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class _MkDocsLoader(yaml.SafeLoader):
    """Read MkDocs environment tags without evaluating environment values."""


_MkDocsLoader.add_constructor("!ENV", lambda loader, node: loader.construct_sequence(node))


def _navigation_markdown_paths(value: object):
    if isinstance(value, dict):
        for child in value.values():
            yield from _navigation_markdown_paths(child)
    elif isinstance(value, list):
        for child in value:
            yield from _navigation_markdown_paths(child)
    elif isinstance(value, str) and value.endswith(".md"):
        yield value


def test_mkdocs_navigation_references_existing_public_docs() -> None:
    config = yaml.load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"), Loader=_MkDocsLoader)

    assert config["site_name"] == "Money Trees · Alpha 810 Research"
    nav_paths = _navigation_markdown_paths(config["nav"])
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
