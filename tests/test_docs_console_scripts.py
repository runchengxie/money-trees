from __future__ import annotations

from pathlib import Path

import tomllib


def test_console_scripts_are_documented() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = sorted(pyproject["project"]["scripts"])
    docs_text = (root / "README.md").read_text(encoding="utf-8")
    for path in sorted((root / "docs").glob("*.md")):
        docs_text += "\n" + path.read_text(encoding="utf-8")

    missing = [script for script in scripts if script not in docs_text]

    assert not missing
