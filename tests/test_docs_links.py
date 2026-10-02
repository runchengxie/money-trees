from __future__ import annotations

import re
from pathlib import Path

import yaml

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


class _MkDocsLoader(yaml.SafeLoader):
    """Read MkDocs environment tags without evaluating environment values."""


_MkDocsLoader.add_constructor("!ENV", lambda loader, node: loader.construct_sequence(node))


def _local_markdown_files(root: Path) -> list[Path]:
    return [
        root / "README.md",
        root / "README.zh-CN.md",
        *sorted((root / "docs").glob("*.md")),
    ]


def test_markdown_internal_links_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    missing: list[str] = []

    for path in _local_markdown_files(root):
        text = path.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = match.group(1).split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            target_path = (path.parent / target).resolve()
            try:
                target_path.relative_to(root.resolve())
            except ValueError:
                continue
            if not target_path.exists():
                missing.append(f"{path.relative_to(root)} -> {target}")

    assert not missing


def test_readme_docs_navigation_mentions_all_user_docs() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    missing = [
        path.name
        for path in sorted((root / "docs").glob("*.md"))
        if not path.name.endswith(".zh-CN.md")
        if f"docs/{path.name}" not in readme
    ]

    assert not missing


def test_root_readme_is_english_canonical_with_chinese_companion() -> None:
    root = Path(__file__).resolve().parents[1]
    english = (root / "README.md").read_text(encoding="utf-8")
    chinese = (root / "README.zh-CN.md").read_text(encoding="utf-8")

    assert english.startswith("# Money Trees")
    assert "[中文页面](README.zh-CN.md)" in english
    assert "[English page](README.md)" in chinese


def test_every_mkdocs_navigation_page_has_a_chinese_companion() -> None:
    root = Path(__file__).resolve().parents[1]
    config = yaml.load((root / "mkdocs.yml").read_text(encoding="utf-8"), Loader=_MkDocsLoader)

    def markdown_paths(value):
        if isinstance(value, dict):
            for child in value.values():
                yield from markdown_paths(child)
        elif isinstance(value, list):
            for child in value:
                yield from markdown_paths(child)
        elif isinstance(value, str) and value.endswith(".md"):
            yield value

    english_paths = set(markdown_paths(config["nav"]))
    locales = config["plugins"][1]["i18n"]["languages"]
    assert locales[0]["locale"] == "en" and locales[0]["default"] is True
    assert locales[1]["locale"] == "zh-CN"
    assert "navigation.instant" not in config["theme"]["features"]
    chinese_paths = set(markdown_paths(locales[1]["nav"]))
    assert chinese_paths == english_paths
    for english_path in english_paths:
        chinese_path = english_path[:-3] + ".zh-CN.md"
        english = (root / "docs" / english_path).read_text(encoding="utf-8")
        chinese = (root / "docs" / chinese_path).read_text(encoding="utf-8")
        stem = english_path.removesuffix(".md")
        chinese_url = (
            f"https://runchengxie.github.io/money-trees/zh-CN/{stem}/"
            if stem != "index"
            else "https://runchengxie.github.io/money-trees/zh-CN/"
        )
        english_url = (
            f"https://runchengxie.github.io/money-trees/{stem}/"
            if stem != "index"
            else "https://runchengxie.github.io/money-trees/"
        )
        assert chinese_url in english
        assert english_url in chinese
