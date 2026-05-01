from __future__ import annotations

from pathlib import Path

import tomllib

HIGH_RISK_FLAGS = {
    "moneytrees-tushare": [
        "--cache-dir",
        "--cache-compression",
        "--cache-compression-level",
        "--cache-row-group-size",
        "--refresh-cache",
        "--refresh-recent-days",
        "--proxy-mode",
        "--proxy-url",
        "--no-fallback-direct",
        "--request-interval-seconds",
        "--rate-limit-retries",
        "--rate-limit-wait-seconds",
        "--sanity-check",
    ],
    "moneytrees-factor-store": [
        "--chunk-trade-dates",
        "--compression",
        "--compression-level",
        "--row-group-size",
        "--overwrite",
    ],
    "moneytrees-dolphindb-alphas": [
        "--factor-store-output",
        "--no-wide-output",
        "--manifest-output",
        "--alpha101-function",
        "--alpha191-function",
        "--wq101-module-version",
        "--gtja191-module-version",
        "--moneytree-alpha-module-version",
        "--stream-input",
        "--dolphindb-warmup-trade-dates",
        "--skip-memory-check",
        "--overwrite",
    ],
    "moneytrees-data-status": [
        "--raw-cache",
        "--factor-store",
        "--artifacts",
        "--factor-family",
        "--skip-factor-quality",
        "--allow-factor-column",
        "--format",
        "--mode",
    ],
    "moneytrees-data-snapshot": [
        "--panel",
        "--raw-cache",
        "--factor-store",
        "--output-dir",
        "--label",
        "--note",
        "--format",
    ],
    "moneytrees-parquet-rewrite": [
        "--compression",
        "--compression-level",
        "--row-group-size",
        "--overwrite",
        "--no-verify",
    ],
}


def _docs_text(root: Path) -> str:
    docs_text = (root / "README.md").read_text(encoding="utf-8")
    for path in sorted((root / "docs").glob("*.md")):
        docs_text += "\n" + path.read_text(encoding="utf-8")
    return docs_text


def test_console_scripts_are_documented() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = sorted(pyproject["project"]["scripts"])
    docs_text = _docs_text(root)

    missing = [script for script in scripts if script not in docs_text]

    assert not missing


def test_high_risk_cli_flags_are_documented() -> None:
    root = Path(__file__).resolve().parents[1]
    docs_text = _docs_text(root)

    missing = [
        f"{command} {flag}"
        for command, flags in HIGH_RISK_FLAGS.items()
        for flag in flags
        if flag not in docs_text
    ]

    assert not missing
