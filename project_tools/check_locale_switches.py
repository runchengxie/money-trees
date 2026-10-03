from __future__ import annotations

import argparse
import re
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import yaml


class _MkDocsLoader(yaml.SafeLoader):
    """Load MkDocs !ENV values without evaluating their environment variables."""


_MkDocsLoader.add_constructor("!ENV", lambda loader, node: loader.construct_sequence(node))


class _LanguageLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        values = dict(attrs)
        if "md-select__link" not in (values.get("class") or "").split():
            return
        language = values.get("hreflang")
        href = values.get("href")
        if language and href:
            self.links[language] = href


def _markdown_paths(value: object):
    if isinstance(value, dict):
        for child in value.values():
            yield from _markdown_paths(child)
    elif isinstance(value, list):
        for child in value:
            yield from _markdown_paths(child)
    elif isinstance(value, str) and value.endswith(".md"):
        yield value


def _route(path: str) -> str:
    stem = Path(path).with_suffix("").as_posix()
    return "/" if stem == "index" else f"/{stem}/"


def _settings(config_path: Path):
    config = yaml.load(config_path.read_text(encoding="utf-8"), Loader=_MkDocsLoader)
    i18n = next(
        plugin["i18n"]
        for plugin in config["plugins"]
        if isinstance(plugin, dict) and "i18n" in plugin
    )
    languages = {language["locale"]: language for language in i18n["languages"]}
    default_locale = next(
        locale for locale, language in languages.items() if language.get("default") is True
    )
    default_base = config["site_url"].rstrip("/") + "/"
    localized = {
        locale: language.get("site_url", f"{default_base}{locale}/").rstrip("/") + "/"
        for locale, language in languages.items()
        if locale != default_locale
    }
    if len(localized) != 1:
        raise ValueError("Expected exactly one non-default locale")
    translated_locale, translated_base = next(iter(localized.items()))

    alternate_codes = {
        alternate["lang"]: alternate["link"] for alternate in config["extra"]["alternate"]
    }
    locale_codes = {
        locale: language.get("theme", {}).get("language", locale)
        for locale, language in languages.items()
    }
    locale_codes[default_locale] = locale_codes[default_locale].split("-")[0]
    code_to_locale = {code: locale for locale, code in locale_codes.items()}
    if set(code_to_locale) != set(alternate_codes):
        raise ValueError("extra.alternate language codes must match the configured locales")

    bases = {default_locale: default_base, translated_locale: translated_base}
    codes = {locale: code for code, locale in code_to_locale.items()}
    return config, default_locale, translated_locale, bases, codes


def _page_html(site_dir: Path, locale: str, default_locale: str, route: str) -> Path:
    prefix = "" if locale == default_locale else f"{locale}/"
    relative_html = "index.html" if route == "/" else f"{route.lstrip('/')}index.html"
    return site_dir / prefix / relative_html


def check_language_switches(site_dir: Path, config_path: Path) -> list[str]:
    config, default_locale, translated_locale, bases, codes = _settings(config_path)
    errors: list[str] = []
    for path in _markdown_paths(config["nav"]):
        route = _route(path)
        for locale in (default_locale, translated_locale):
            html_path = _page_html(site_dir, locale, default_locale, route)
            if not html_path.is_file():
                errors.append(f"Missing rendered {locale} page: {html_path}")
                continue
            parser = _LanguageLinks()
            parser.feed(html_path.read_text(encoding="utf-8"))
            page_url = bases[locale].rstrip("/") + route
            for target_locale in (default_locale, translated_locale):
                href = parser.links.get(codes[target_locale])
                expected = bases[target_locale].rstrip("/") + route
                actual = urljoin(page_url, href) if href else None
                if actual != expected:
                    errors.append(
                        f"{locale} page {route} links to {target_locale} at {actual!r}; "
                        f"expected {expected!r} (href={href!r}, page={html_path})"
                    )
    return errors


def synchronize_language_switches(site_dir: Path, config_path: Path) -> list[str]:
    config, default_locale, translated_locale, bases, codes = _settings(config_path)
    errors: list[str] = []
    for path in _markdown_paths(config["nav"]):
        route = _route(path)
        for locale in (default_locale, translated_locale):
            html_path = _page_html(site_dir, locale, default_locale, route)
            if not html_path.is_file():
                errors.append(f"Missing rendered {locale} page: {html_path}")
                continue
            text = html_path.read_text(encoding="utf-8")
            for target_locale in (default_locale, translated_locale):
                code = re.escape(codes[target_locale])
                pattern = re.compile(
                    rf'(<a href=")[^"]*(" hreflang="{code}" class="md-select__link">)'
                )
                target = escape(bases[target_locale].rstrip("/") + route, quote=True)
                text, count = pattern.subn(rf"\g<1>{target}\g<2>", text)
                if count != 1:
                    errors.append(
                        f"Expected one {codes[target_locale]} language link in {html_path}; "
                        f"found {count}"
                    )
            html_path.write_text(text, encoding="utf-8")
    errors.extend(check_language_switches(site_dir, config_path))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Point localized pages to their same-page language alternates."
    )
    parser.add_argument("site_dir", type=Path)
    parser.add_argument("--config", type=Path, default=Path("mkdocs.yml"))
    args = parser.parse_args()
    errors = synchronize_language_switches(args.site_dir, args.config)
    if errors:
        print("\n".join(errors))
        return 1
    print("All configured pages link to their same-page language alternates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
