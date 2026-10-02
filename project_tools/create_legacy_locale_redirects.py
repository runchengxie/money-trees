"""Keep old ``*.zh-CN/`` documentation URLs working after locale routing."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def create_redirects(docs_dir: Path, site_dir: Path) -> int:
    count = 0
    for source in sorted(docs_dir.glob("*.zh-CN.md")):
        stem = source.name.removesuffix(".zh-CN.md")
        destination = f"/money-trees/zh-CN/{stem}/" if stem != "index" else "/money-trees/zh-CN/"
        target = site_dir / f"{stem}.zh-CN" / "index.html"
        if target.exists():
            raise ValueError(f"Refusing to overwrite generated page: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        escaped = html.escape(destination, quote=True)
        target.write_text(
            "<!doctype html>\n"
            '<html lang="zh-CN"><head><meta charset="utf-8">\n'
            f'<meta http-equiv="refresh" content="0;url={escaped}">\n'
            f"<script>location.replace({json.dumps(destination)} + location.search + location.hash)</script>\n"
            f'<link rel="canonical" href="https://runchengxie.github.io{escaped}">\n'
            "</head><body>"
            f'<a href="{escaped}">打开中文页面</a>'
            "</body></html>\n",
            encoding="utf-8",
        )
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-dir", type=Path, default=Path("docs"))
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    args = parser.parse_args()
    print(f"Created {create_redirects(args.docs_dir, args.site_dir)} legacy locale redirects")


if __name__ == "__main__":
    main()
