from __future__ import annotations

from pathlib import Path

import yaml

from project_tools.check_locale_switches import (
    check_language_switches,
    synchronize_language_switches,
)

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
    assert "SEARCH_LANG=en" in workflow
    assert "SEARCH_LANG=zh" in workflow
    assert "actions/upload-pages-artifact" in workflow
    assert "actions/deploy-pages" in workflow


def test_locale_switch_checker_accepts_page_routes_and_rejects_homepage_links(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site"
    english_page = site / "cli-reference" / "index.html"
    chinese_page = site / "zh-CN" / "cli-reference" / "index.html"
    english_page.parent.mkdir(parents=True)
    chinese_page.parent.mkdir(parents=True)
    english_page.write_text(
        '<a href="./" hreflang="en" class="md-select__link">English</a>'
        '<a href="https://example.org/docs/zh-CN/" hreflang="zh" class="md-select__link">中文</a>',
        encoding="utf-8",
    )
    chinese_page.write_text(
        '<a href="../../cli-reference/" hreflang="en" class="md-select__link">English</a>'
        '<a href="./" hreflang="zh" class="md-select__link">中文</a>',
        encoding="utf-8",
    )
    config = tmp_path / "mkdocs.yml"
    config.write_text(
        "site_url: https://example.org/docs/\n"
        "plugins:\n"
        "  - i18n:\n"
        "      languages:\n"
        "        - locale: en\n"
        "          default: true\n"
        "        - locale: zh-CN\n"
        "          site_url: https://example.org/docs/zh-CN/\n"
        "          theme:\n"
        "            language: zh\n"
        "extra:\n"
        "  alternate:\n"
        "    - name: English\n"
        "      link: https://example.org/docs/\n"
        "      lang: en\n"
        "    - name: 简体中文\n"
        "      link: https://example.org/docs/zh-CN/\n"
        "      lang: zh\n"
        "nav:\n"
        "  - CLI reference: cli-reference.md\n",
        encoding="utf-8",
    )

    errors = check_language_switches(site, config)
    assert len(errors) == 1
    assert "expected 'https://example.org/docs/zh-CN/cli-reference/'" in errors[0]
    assert synchronize_language_switches(site, config) == []
    assert check_language_switches(site, config) == []

    chinese_page.write_text(
        '<a href="https://example.org/docs/" hreflang="en" class="md-select__link">English</a>'
        '<a href="https://example.org/docs/zh-CN/" hreflang="zh" class="md-select__link">中文</a>',
        encoding="utf-8",
    )
    errors = check_language_switches(site, config)
    assert len(errors) == 2
    assert "expected 'https://example.org/docs/cli-reference/'" in errors[0]
