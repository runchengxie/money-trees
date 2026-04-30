from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from moneytree.data import DEFAULT_PARQUET_COMPRESSION, load_market_data
from moneytree.factor_store import (
    LOCAL_FACTOR_FAMILIES,
    write_local_factor_store,
    write_local_factor_store_from_parquet,
)


@dataclass(frozen=True)
class FactorStoreBuildResult:
    manifest_path: Path
    base_rows: int
    factor_families: tuple[str, ...]


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate local Alpha158/Alpha360 factor-store files from a Money Trees base panel."
        )
    )
    parser.add_argument("--input", required=True, help="Input base panel parquet or pickle.")
    parser.add_argument("--output-dir", required=True, help="Output factor-store directory.")
    parser.add_argument(
        "--factor-family",
        action="append",
        default=[],
        choices=LOCAL_FACTOR_FAMILIES,
        help="Local factor family to generate. Repeatable.",
    )
    parser.add_argument(
        "--raw-features",
        action="store_true",
        help="Use raw OHLCV/VWAP fields instead of adjusted price fields for local factors.",
    )
    parser.add_argument(
        "--factor-dtype",
        default="float32",
        choices=["float32", "float64"],
        help="Dtype for generated factor columns.",
    )
    parser.add_argument(
        "--chunk-trade-dates",
        type=_positive_int,
        default=60,
        help="Number of target trade dates per factor partition.",
    )
    parser.add_argument(
        "--compression",
        default=DEFAULT_PARQUET_COMPRESSION,
        help="Parquet compression codec.",
    )
    parser.add_argument(
        "--compression-level",
        type=_positive_int,
        default=None,
        help="Parquet compression level. Defaults to 3 for zstd.",
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
        help="Regenerate requested factor families even when they already exist in the store.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print factor generation progress to stderr.",
    )
    return parser


def run_generation(args: argparse.Namespace) -> FactorStoreBuildResult:
    families = tuple(args.factor_family or ())
    if not families:
        raise ValueError("At least one --factor-family is required.")

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    metadata = {
        "source": "moneytrees-factor-store",
        "input": str(input_path),
    }
    if input_path.suffix.lower() == ".parquet":
        manifest = write_local_factor_store_from_parquet(
            input_path,
            output_dir,
            families=families,
            adjusted=not bool(args.raw_features),
            factor_dtype=args.factor_dtype,
            chunk_trade_dates=int(args.chunk_trade_dates),
            compression=args.compression,
            compression_level=args.compression_level,
            row_group_size=args.row_group_size,
            overwrite=bool(args.overwrite),
            show_progress=bool(args.progress),
            metadata=metadata,
        )
    else:
        panel = load_market_data(input_path)
        manifest = write_local_factor_store(
            panel,
            output_dir,
            families=families,
            adjusted=not bool(args.raw_features),
            factor_dtype=args.factor_dtype,
            chunk_trade_dates=int(args.chunk_trade_dates),
            compression=args.compression,
            compression_level=args.compression_level,
            row_group_size=args.row_group_size,
            overwrite=bool(args.overwrite),
            show_progress=bool(args.progress),
            metadata=metadata,
        )
    return FactorStoreBuildResult(
        manifest_path=output_dir / "manifest.json",
        base_rows=int(manifest["base_panel"]["rows"]),
        factor_families=tuple(sorted(manifest.get("factor_families", {}))),
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_generation(args)
    except ValueError as exc:
        parser.error(str(exc))
    print(
        "Saved factor store "
        f"rows={result.base_rows} "
        f"families={','.join(result.factor_families)} "
        f"manifest={result.manifest_path}"
    )


if __name__ == "__main__":
    main()
