from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Sequence

from moneytree.data import DEFAULT_PARQUET_COMPRESSION
from moneytree.data import load_market_data
from moneytree.data import save_market_data


@dataclass(frozen=True)
class RewriteResult:
    input_path: Path
    output_path: Path
    rows: int
    columns: int
    compression: str
    compression_level: int | None


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rewrite a Money Trees parquet/pickle dataset to parquet with chosen options."
    )
    parser.add_argument("--input", required=True, help="Input parquet or pickle path.")
    parser.add_argument("--output", required=True, help="Output parquet path.")
    parser.add_argument(
        "--compression",
        default=DEFAULT_PARQUET_COMPRESSION,
        help="Output parquet compression codec. Default: zstd.",
    )
    parser.add_argument(
        "--compression-level",
        type=_positive_int,
        default=None,
        help="Output parquet compression level. Defaults to 3 for zstd.",
    )
    parser.add_argument(
        "--row-group-size",
        type=_positive_int,
        default=None,
        help="Optional parquet row group size in rows.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing output path. In-place rewrites are still refused.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-write shape and key verification.",
    )
    return parser


def _verify_rewrite(source, rewritten) -> None:
    if len(source) != len(rewritten):
        raise ValueError(f"Verification failed: rows {len(rewritten)} != {len(source)}.")
    if list(source.columns) != list(rewritten.columns):
        raise ValueError("Verification failed: output columns differ from input columns.")
    if list(source.index.names) != list(rewritten.index.names):
        raise ValueError("Verification failed: output index names differ from input index names.")


def run_rewrite(args: argparse.Namespace) -> RewriteResult:
    input_path = Path(args.input)
    output_path = Path(args.output)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Refusing in-place rewrite; write to a new output path first.")
    if output_path.exists() and not bool(args.overwrite):
        raise ValueError(f"Output already exists: {output_path}. Pass --overwrite to replace it.")

    frame = load_market_data(input_path)
    save_market_data(
        frame,
        output_path,
        compression=args.compression,
        compression_level=args.compression_level,
        row_group_size=args.row_group_size,
    )
    if not bool(args.no_verify):
        _verify_rewrite(frame, load_market_data(output_path))

    return RewriteResult(
        input_path=input_path,
        output_path=output_path,
        rows=int(len(frame)),
        columns=int(len(frame.columns)),
        compression=str(args.compression),
        compression_level=args.compression_level,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_rewrite(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    level = result.compression_level if result.compression_level is not None else "default"
    print(
        "Saved parquet "
        f"rows={result.rows} cols={result.columns} "
        f"compression={result.compression} compression_level={level} "
        f"input={result.input_path} output={result.output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
