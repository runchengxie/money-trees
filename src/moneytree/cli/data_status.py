from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from moneytree.data_quality import DATA_QUALITY_MODES, validate_data_quality_mode
from moneytree.data_status import build_data_status_report


def _csv_values(values: Sequence[str] | None) -> set[str]:
    found: set[str] = set()
    for value in values or ():
        for item in str(value).split(","):
            normalized = item.strip()
            if normalized:
                found.add(normalized)
    return found


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect Money Trees data layers without modifying files."
    )
    parser.add_argument("--panel", help="Base date,ticker panel parquet or pickle path.")
    parser.add_argument("--raw-cache", help="TuShare raw cache directory or manifest.sqlite path.")
    parser.add_argument("--factor-store", help="Factor-store directory or manifest.json path.")
    parser.add_argument("--artifacts", help="Backtest artifact directory.")
    parser.add_argument(
        "--factor-family",
        "--factor-families",
        action="append",
        default=[],
        metavar="FAMILY[,FAMILY...]",
        help=(
            "Only inspect selected factor-store families. Can be repeated or comma-separated, "
            "for example --factor-family alpha191,alpha360."
        ),
    )
    parser.add_argument(
        "--skip-factor-quality",
        action="store_true",
        help="Only validate factor-store manifest paths and row metadata; skip value scans.",
    )
    parser.add_argument(
        "--allow-factor-column",
        action="append",
        default=[],
        metavar="COLUMN[,COLUMN...]",
        help=(
            "Treat known all-null/high-null/constant factor columns as allowed. Can be "
            "repeated or comma-separated."
        ),
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print factor-store quality scan progress to stderr.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format. Default: text.",
    )
    parser.add_argument(
        "--mode",
        choices=DATA_QUALITY_MODES,
        default="warn",
        help="Exit behavior for reported data errors. Default: warn.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not any((args.panel, args.raw_cache, args.factor_store, args.artifacts)):
        parser.error(
            "At least one data layer path is required: --panel, --raw-cache, "
            "--factor-store, or --artifacts."
        )
    mode = validate_data_quality_mode(args.mode)
    try:
        report = build_data_status_report(
            panel=Path(args.panel) if args.panel else None,
            raw_cache=Path(args.raw_cache) if args.raw_cache else None,
            factor_store=Path(args.factor_store) if args.factor_store else None,
            artifacts=Path(args.artifacts) if args.artifacts else None,
            factor_families=_csv_values(args.factor_family),
            check_factor_quality=not args.skip_factor_quality,
            allowed_factor_columns=_csv_values(args.allow_factor_column),
            show_progress=bool(args.progress),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for line in report.to_lines():
            print(line)

    if mode == "error" and not report.ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
