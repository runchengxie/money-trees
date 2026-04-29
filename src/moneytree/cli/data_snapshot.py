from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from moneytree.data_snapshot import create_data_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a Money Trees data snapshot manifest with metadata and checksums. "
            "Large data files are referenced, not copied."
        )
    )
    parser.add_argument("--panel", required=True, help="Base date,ticker panel parquet or pickle path.")
    parser.add_argument("--output-dir", required=True, help="Directory for snapshot metadata files.")
    parser.add_argument("--raw-cache", help="Optional TuShare raw cache directory or manifest.sqlite path.")
    parser.add_argument("--factor-store", help="Optional factor-store directory or manifest.json path.")
    parser.add_argument("--label", default="", help="Optional human-readable snapshot label.")
    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="Optional note to include in dataset_meta.json and README.md. Repeatable.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format. Default: text.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = create_data_snapshot(
            panel=Path(args.panel),
            output_dir=Path(args.output_dir),
            raw_cache=Path(args.raw_cache) if args.raw_cache else None,
            factor_store=Path(args.factor_store) if args.factor_store else None,
            label=args.label or None,
            notes=list(args.note or ()),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(result.manifest, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        panel = result.manifest["panel"]
        print(
            "Saved data snapshot "
            f"rows={panel.get('rows')} cols={panel.get('columns')} "
            f"start={panel.get('date_min') or 'NA'} end={panel.get('date_max') or 'NA'} "
            f"manifest={result.manifest_path}"
        )
        print(f"Checksums: {result.checksums_path}")
        print(f"README: {result.readme_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
