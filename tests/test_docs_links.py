from __future__ import annotations

import re
from pathlib import Path

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


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
