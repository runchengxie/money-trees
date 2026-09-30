from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

INDIRECT_CONTRAST_RE = re.compile(r"(不是.{0,80}而是|而不是)")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
PARENTHETICAL_EN_RE = re.compile(r"[（(][A-Za-z0-9 _./-]+[）)]")
URL_RE = re.compile(r"https?://\S+")

TERM_DRIFT_PATTERNS = {
    "factor store": "因子仓库",
    "raw cache": "原始缓存",
    "manifest": "元数据清单",
    "artifacts": "回测产物",
    "holdout": "留出验证",
    "panel": "面板",
    "preset": "预设配置",
    "family": "因子族",
    "backlog": "待办",
    "dry-run": "只预览",
}


def test_mkdocs_supports_system_theme_with_manual_dark_mode_toggle() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / "mkdocs.yml").read_text(encoding="utf-8")

    assert 'media: "(prefers-color-scheme: light)"' in config
    assert 'media: "(prefers-color-scheme: dark)"' in config
    assert "scheme: slate" in config
    assert "Switch to dark mode" in config
    assert "Switch to light mode" in config


def _docs_paths(root: Path) -> list[Path]:
    return [
        root / "README.md",
        root / "README.zh-CN.md",
        root / "AGENTS.md",
        *sorted((root / "docs").glob("*.md")),
    ]


def _prose_lines(path: Path) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = URL_RE.sub("", line)
        stripped = INLINE_CODE_RE.sub("", stripped)
        stripped = PARENTHETICAL_EN_RE.sub("", stripped)
        lines.append((lineno, stripped))
    return lines


def test_docs_avoid_indirect_contrast_pattern() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in _docs_paths(root):
        for lineno, line in _prose_lines(path):
            if INDIRECT_CONTRAST_RE.search(line):
                offenders.append(f"{path.relative_to(root)}:{lineno}: {line.strip()}")

    assert not offenders


def test_chinese_docs_use_project_terms_for_factor_store() -> None:
    root = Path(__file__).resolve().parents[1]
    docs_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            root / "README.md",
            root / "README.zh-CN.md",
            *sorted((root / "docs").glob("*.md")),
        ]
    )

    assert "因子仓库" in docs_text
    assert "市场配置档" in docs_text
    assert "可交易过滤" in docs_text


def test_chinese_docs_avoid_core_term_drift() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in _docs_paths(root):
        for lineno, line in _prose_lines(path):
            if not CHINESE_RE.search(line):
                continue
            lowered = line.lower()
            for english, chinese in TERM_DRIFT_PATTERNS.items():
                if english in lowered:
                    offenders.append(
                        f"{path.relative_to(root)}:{lineno}: use {chinese!r} "
                        f"instead of {english!r}: {line.strip()}"
                    )

    assert not offenders


def test_dolphindb_module_docs_match_repository_files() -> None:
    root = Path(__file__).resolve().parents[1]
    module_dir = root / "docker" / "dolphindb" / "modules"
    expected = {
        "wq101alpha.dos",
        "prepare101.dos",
        "gtja191Alpha.dos",
        "gtja191Prepare.dos",
        "moneytreeAlpha.dos",
    }
    present = {path.name for path in module_dir.glob("*.dos")}
    if not expected <= present:
        pytest.skip(
            "DolphinDB module files are gitignored and only exist in a prepared "
            "local checkout"
        )
    doc = (root / "docs" / "generate-alpha101-191-with-dolphindb.md").read_text(
        encoding="utf-8"
    )

    assert "这些 `.dos` 文件不提交到仓库" not in doc
    assert "本地准备、不随仓库提交" in doc


def test_factor_catalog_external_status_matches_docs() -> None:
    root = Path(__file__).resolve().parents[1]
    catalog_doc = (root / "docs" / "factor-catalog.md").read_text(encoding="utf-8")
    catalog_path = root / "docs" / "factor-catalog.csv"
    with catalog_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    alpha_statuses = {
        row["formula_status"]
        for row in rows
        if row["family"] in {"alpha101", "alpha191"}
    }

    assert alpha_statuses == {"implemented_local"}
    assert "src/moneytree/factors/classic.py" in catalog_doc
    assert "DolphinDB" in catalog_doc
    assert "external_not_stored" not in catalog_doc
