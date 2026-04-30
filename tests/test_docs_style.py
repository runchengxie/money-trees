from __future__ import annotations

import re
from pathlib import Path

INDIRECT_CONTRAST_RE = re.compile(r"不是.{0,80}而是")


def test_docs_avoid_indirect_contrast_pattern() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in [root / "README.md", root / "AGENTS.md", *sorted((root / "docs").glob("*.md"))]:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if INDIRECT_CONTRAST_RE.search(line):
                offenders.append(f"{path.relative_to(root)}:{lineno}: {line.strip()}")

    assert not offenders


def test_chinese_docs_use_project_terms_for_factor_store() -> None:
    root = Path(__file__).resolve().parents[1]
    docs_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [root / "README.md", *sorted((root / "docs").glob("*.md"))]
    )

    assert "因子仓库" in docs_text
    assert "市场配置档" in docs_text
    assert "可交易过滤" in docs_text
