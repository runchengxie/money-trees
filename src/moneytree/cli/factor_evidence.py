from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from moneytree.data import load_market_data
from moneytree.factors.evidence_v1 import build_factor_evidence_v1
from moneytree.factors.publication import (
    audit_public_snapshot,
    build_factor_evidence_snapshot,
)
from moneytree.factors.store_publication import (
    build_factor_evidence_snapshot_from_archive,
    build_factor_evidence_snapshot_from_store,
    build_signal_quality_report,
)


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
    source.add_argument(
        "--factor-store-archive",
        help="Uncompressed tar archive containing a factor store; reads members without unpacking the archive.",
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
    parser.add_argument(
        "--benchmark-return-column",
        help="Optional realized daily benchmark return column for market-regime slices.",
    )
    parser.add_argument("--benchmark-name", help="Human-readable benchmark identifier.")
    parser.add_argument(
        "--regime-window", type=int, default=252, help="Prior trading days used for regime labels."
    )
    parser.add_argument(
        "--holding-period-days",
        type=int,
        help="Forward-return holding period; required before inferential diagnostics are emitted.",
    )
    parser.add_argument("--data-version", default="unknown", help="Input data version label.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument(
        "--quality-output", help="Optional aggregate-only signal quality report JSON path."
    )
    parser.add_argument(
        "--evidence-v1-output",
        help="Optional unified factor_evidence.v1 JSON output path.",
    )
    parser.add_argument("--group-count", type=int, default=5, help="Number of return groups.")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    return parser


def _factor_names(value: str) -> list[str]:
    path = Path(value)
    if path.is_file():
        return [
            line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.factor_store or args.factor_store_archive:
            if args.factors not in {"all", "*"}:
                raise ValueError(
                    "--factors must be 'all' or '*' when using --factor-store or --factor-store-archive"
                )
            families = args.families.split(",") if args.families else None
            if args.factor_store:
                payload = build_factor_evidence_snapshot_from_store(
                    Path(args.factor_store),
                    families=families,
                    date_start=args.date_start,
                    date_end=args.date_end,
                    return_column=args.return_column,
                    data_version=args.data_version,
                    group_count=args.group_count,
                    benchmark_return_column=args.benchmark_return_column,
                    benchmark_name=args.benchmark_name,
                    regime_window=args.regime_window,
                    holding_period_days=args.holding_period_days,
                )
            else:
                payload = build_factor_evidence_snapshot_from_archive(
                    Path(args.factor_store_archive),
                    families=families,
                    date_start=args.date_start,
                    date_end=args.date_end,
                    return_column=args.return_column,
                    data_version=args.data_version,
                    group_count=args.group_count,
                    benchmark_return_column=args.benchmark_return_column,
                    benchmark_name=args.benchmark_name,
                    regime_window=args.regime_window,
                    holding_period_days=args.holding_period_days,
                )
        else:
            panel = load_market_data(Path(args.panel))
            payload = build_factor_evidence_snapshot(
                panel,
                _factor_names(args.factors),
                return_column=args.return_column,
                data_version=args.data_version,
                config={"group_count": args.group_count},
                benchmark_return_column=args.benchmark_return_column,
                benchmark_name=args.benchmark_name,
                regime_window=args.regime_window,
                holding_period_days=args.holding_period_days,
            )
        audit_public_snapshot(payload)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if args.quality_output:
            quality_output = Path(args.quality_output)
            quality_output.parent.mkdir(parents=True, exist_ok=True)
            quality_output.write_text(
                json.dumps(
                    build_signal_quality_report(payload),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        if args.evidence_v1_output:
            evidence_output = Path(args.evidence_v1_output)
            evidence_output.parent.mkdir(parents=True, exist_ok=True)
            evidence_output.write_text(
                json.dumps(build_factor_evidence_v1(payload), ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
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
