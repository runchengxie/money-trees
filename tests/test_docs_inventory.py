from __future__ import annotations

from pathlib import Path


def test_testing_doc_mentions_all_test_files() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = (root / "docs/testing.md").read_text(encoding="utf-8")
    missing = [
        path.name
        for path in sorted((root / "tests").glob("test_*.py"))
        if path.name not in doc
    ]

    assert not missing
