from __future__ import annotations

from pathlib import Path

import pytest

from project_tools.create_legacy_locale_redirects import create_redirects


def test_old_chinese_page_urls_redirect_to_language_routes(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    site = tmp_path / "site"
    docs.mkdir()
    (docs / "index.zh-CN.md").write_text("# 首页\n", encoding="utf-8")
    (docs / "cli-reference.zh-CN.md").write_text("# CLI 参考\n", encoding="utf-8")

    assert create_redirects(docs, site) == 2
    home = (site / "index.zh-CN" / "index.html").read_text(encoding="utf-8")
    cli = (site / "cli-reference.zh-CN" / "index.html").read_text(encoding="utf-8")
    assert "/money-trees/zh-CN/" in home
    assert "/money-trees/zh-CN/cli-reference/" in cli
    assert "location.search + location.hash" in cli
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        create_redirects(docs, site)
