from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from moneytree.data import load_market_data
from moneytree.factors.publication import (
    audit_public_snapshot,
    build_factor_evidence_snapshot,
)
from moneytree.factors.store_publication import build_factor_evidence_snapshot_from_store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an aggregate-only public Alpha factor evidence snapshot."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--panel", help="Panel parquet or trusted pickle path.")
    source.add_argument(
        "--factor-store",
        help="Partitioned factor-store manifest.json; reads factor partitions incrementally.",
    )
    parser.add_argument(
        "--families",
        help="Comma-separated factor families when using --factor-store; defaults to all.",
    )
    parser.add_argument("--date-start", help="Optional inclusive date filter for --factor-store.")
    parser.add_argument("--date-end", help="Optional inclusive date filter for --factor-store.")
    parser.add_argument(
        "--factors",
        required=True,
        help="Comma-separated factor names or a text file with one factor per line.",
    )
    parser.add_argument(
        "--return-column", default="next_period_return", help="Forward return column."
    )
    parser.add_argument("--data-version", default="unknown", help="Input data version label.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--group-count", type=int, default=5, help="Number of return groups.")
    parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format."
    )
    return parser


def _factor_names(value: str) -> list[str]:
    path = Path(value)
    if path.is_file():
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.factor_store:
            if args.factors not in {"all", "*"}:
                raise ValueError("--factors must be 'all' or '*' when using --factor-store")
            families = args.families.split(",") if args.families else None
            payload = build_factor_evidence_snapshot_from_store(
                Path(args.factor_store),
                families=families,
                date_start=args.date_start,
                date_end=args.date_end,
                return_column=args.return_column,
                data_version=args.data_version,
                group_count=args.group_count,
            )
        else:
            panel = load_market_data(Path(args.panel))
            payload = build_factor_evidence_snapshot(
                panel,
                _factor_names(args.factors),
                return_column=args.return_column,
                data_version=args.data_version,
                config={"group_count": args.group_count},
            )
        audit_public_snapshot(payload)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "Saved factor evidence snapshot "
            f"factors={len(payload['factors'])} "
            f"start={payload['dataset']['date_start'] or 'NA'} "
            f"end={payload['dataset']['date_end'] or 'NA'} "
            f"output={output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
