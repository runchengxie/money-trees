"""Verify that deployed documentation keeps search within the current locale."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

SITE = Path(__file__).resolve().parents[1] / "site"
BASE_URL = "https://runchengxie.github.io/money-trees/"
CONFIG_RE = re.compile(r'<script id="__config" type="application/json">(.*?)</script>')


def _check_locale(root: Path, locale: str, title: str) -> None:
    index_path = root / "search" / "search_index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    entries = payload["docs"]
    assert entries, f"empty search index: {index_path}"
    assert payload["config"]["lang"] == ["zh" if locale == "zh" else "en"]
    if locale == "zh":
        assert (root / "assets/javascripts/lunr/min/lunr.zh.min.js").is_file()
        assert any("\u200b" in entry["text"] for entry in entries)
    for entry in entries:
        url = urlsplit(entry["location"])
        relative = Path(unquote(url.path))
        assert not relative.is_absolute() and ".." not in relative.parts, entry["location"]
        assert (root / relative / "index.html").is_file(), entry["location"]

    cli = (root / "cli-reference" / "index.html").read_text(encoding="utf-8")
    expected_url = BASE_URL + ("zh-CN/" if locale == "zh" else "") + "cli-reference/"
    assert f'<html lang="{locale}"' in cli
    assert f'<link rel="canonical" href="{expected_url}">' in cli
    assert "md-select__link" in cli
    assert BASE_URL + "zh-CN/" in cli and BASE_URL in cli

    match = CONFIG_RE.search(cli)
    assert match is not None, "missing Material search configuration"
    config = json.loads(match.group(1))
    search_path = (root / "cli-reference" / config["base"] / "search/search_index.json").resolve()
    assert search_path == index_path.resolve(), search_path
    indexed_title = next(entry for entry in entries if entry["location"] == "cli-reference/")[
        "title"
    ]
    assert indexed_title.replace("\u200b", "") == title


def main() -> None:
    _check_locale(SITE, "en", "CLI reference")
    _check_locale(SITE / "zh-CN", "zh", "CLI 参考")


if __name__ == "__main__":
    main()
