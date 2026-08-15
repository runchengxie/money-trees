from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from moneytree.data import (
    DEFAULT_PARQUET_COMPRESSION,
    coerce_factor_columns,
    load_market_data,
    normalize_factor_dtype,
    save_market_data,
)
from moneytree.factor_store import write_external_factor_store
from moneytree.factors.classic import build_classic_alpha_features
from moneytree.factors.external import (
    build_external_alpha_manifest,
    external_alpha_columns,
    merge_external_alpha_columns,
    normalize_external_families,
    write_external_alpha_manifest,
)

FACTOR_SOURCE = "python"


@dataclass(frozen=True)
class GenerationResult:
    output_path: Path | None
    manifest_path: Path | None
    rows: int
    alpha_columns: int
    factor_store_manifest_path: Path | None = None


def _selected_families(args: argparse.Namespace) -> list[str]:
    requested = list(args.family or [])
    if args.alpha101:
        requested.append("alpha101")
    if args.alpha191:
        requested.append("alpha191")
    return normalize_external_families(requested)


def _family_alpha_column_count(families: Sequence[str]) -> int:
    return sum(len(external_alpha_columns(family)) for family in families)


def _family_validation_summary(factor_frame, families: Sequence[str]) -> dict[str, object]:
    family_results: dict[str, object] = {}
    for family in families:
        columns = external_alpha_columns(family)
        present = [column for column in columns if column in factor_frame.columns]
        non_null = int(factor_frame[present].notna().sum().sum()) if present else 0
        family_results[family] = {
            "columns": len(columns),
            "present_columns": len(present),
            "non_null_values": non_null,
        }
    return {
        "families": list(families),
        "family_results": family_results,
        "factor_source": FACTOR_SOURCE,
    }


def run_generation(args: argparse.Namespace) -> GenerationResult:
    families = _selected_families(args)
    if not families:
        raise ValueError("At least one alpha family is required: --alpha101, --alpha191, or --family.")
    factor_dtype = normalize_factor_dtype(getattr(args, "factor_dtype", "float32"))
    use_adjusted_prices = not bool(getattr(args, "raw_price_fields", False))

    input_path = Path(args.input)
    no_wide_output = bool(getattr(args, "no_wide_output", False))
    factor_store_output = getattr(args, "factor_store_output", None)
    if no_wide_output and not factor_store_output:
        raise ValueError("--no-wide-output requires --factor-store-output.")
    if no_wide_output and getattr(args, "output", None):
        raise ValueError("--no-wide-output cannot be combined with --output.")
    if not getattr(args, "output", None) and not factor_store_output:
        raise ValueError("At least one output target is required: --output or --factor-store-output.")

    output_path = Path(args.output) if getattr(args, "output", None) and not no_wide_output else None
    manifest_path = (
        (
            Path(args.manifest_output)
            if args.manifest_output
            else output_path.with_suffix(output_path.suffix + ".factor_manifest.json")
        )
        if output_path is not None
        else None
    )

    panel = load_market_data(input_path)
    factor_frame = build_classic_alpha_features(
        panel,
        families,
        adjusted=use_adjusted_prices,
        dtype=factor_dtype,
        show_progress=bool(getattr(args, "progress", False)),
    )

    factor_store_manifest_path: Path | None = None
    if no_wide_output and factor_store_output:
        store_dir = Path(factor_store_output)
        write_external_factor_store(
            panel,
            factor_frame,
            store_dir,
            families=families,
            factor_dtype=factor_dtype,
            chunk_trade_dates=int(getattr(args, "chunk_trade_dates", 60)),
            compression=args.compression,
            compression_level=getattr(args, "compression_level", None),
            row_group_size=getattr(args, "row_group_size", None),
            overwrite=bool(getattr(args, "overwrite", False)),
            show_progress=bool(getattr(args, "progress", False)),
            source=FACTOR_SOURCE,
        )
        factor_store_manifest_path = store_dir / "manifest.json"
        return GenerationResult(
            output_path=None,
            manifest_path=None,
            rows=int(len(panel)),
            alpha_columns=_family_alpha_column_count(families),
            factor_store_manifest_path=factor_store_manifest_path,
        )

    merged, validation = merge_external_alpha_columns(panel, factor_frame, families)
    merged = coerce_factor_columns(merged, factor_dtype)

    if output_path is not None and manifest_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temp_paths: list[Path] = []
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                dir=output_path.parent,
                delete=False,
            ) as handle:
                temp_output = Path(handle.name)
            temp_paths.append(temp_output)
            save_market_data(
                merged,
                temp_output,
                compression=args.compression,
                compression_level=getattr(args, "compression_level", None),
                row_group_size=getattr(args, "row_group_size", None),
            )

            manifest = build_external_alpha_manifest(
                input_path=input_path,
                output_path=temp_output,
                input_frame=panel,
                output_frame=merged,
                families=families,
                field_mapping={},
                validation=_family_validation_summary(factor_frame, families),
                factor_source=FACTOR_SOURCE,
                source_metadata={
                    "use_adjusted_prices": bool(use_adjusted_prices),
                    "families": list(families),
                },
            )
            manifest["output_data"]["path"] = str(output_path)
            manifest["output_data"]["compression"] = args.compression
            manifest["output_data"]["compression_level"] = getattr(args, "compression_level", None)
            manifest["output_data"]["row_group_size"] = getattr(args, "row_group_size", None)
            manifest["factor_dtype"] = factor_dtype

            with tempfile.NamedTemporaryFile(
                prefix=f".{manifest_path.name}.",
                suffix=".tmp",
                dir=manifest_path.parent,
                delete=False,
            ) as handle:
                temp_manifest = Path(handle.name)
            temp_paths.append(temp_manifest)
            write_external_alpha_manifest(manifest, temp_manifest)

            temp_output.replace(output_path)
            temp_manifest.replace(manifest_path)
            temp_paths.clear()
        finally:
            for path in temp_paths:
                path.unlink(missing_ok=True)

    if factor_store_output:
        store_dir = Path(factor_store_output)
        write_external_factor_store(
            panel,
            factor_frame,
            store_dir,
            families=families,
            factor_dtype=factor_dtype,
            chunk_trade_dates=int(getattr(args, "chunk_trade_dates", 60)),
            compression=args.compression,
            compression_level=getattr(args, "compression_level", None),
            row_group_size=getattr(args, "row_group_size", None),
            overwrite=bool(getattr(args, "overwrite", False)),
            show_progress=bool(getattr(args, "progress", False)),
            source=FACTOR_SOURCE,
        )
        factor_store_manifest_path = store_dir / "manifest.json"

    alpha_columns = [
        column
        for column in merged.columns
        if str(column).startswith(("alpha101_", "alpha191_"))
    ]
    return GenerationResult(
        output_path=output_path,
        manifest_path=manifest_path,
        rows=int(len(merged)),
        alpha_columns=len(alpha_columns),
        factor_store_manifest_path=factor_store_manifest_path,
    )


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Alpha101/Alpha191 factors in pure Python with cross-sectional "
            "rank/scale semantics and merge them into a Money Trees panel or factor store."
        ),
    )
    parser.add_argument("--input", required=True, help="Input Money Trees panel parquet or pickle.")
    parser.add_argument("--output", help="Output merged panel parquet.")
    parser.add_argument(
        "--manifest-output",
        help="Manifest JSON path. Defaults to <output>.factor_manifest.json.",
    )
    parser.add_argument(
        "--factor-store-output",
        help="Output factor-store directory for generated Alpha101/191 families.",
    )
    parser.add_argument(
        "--no-wide-output",
        action="store_true",
        help="Write only --factor-store-output and skip the merged wide panel.",
    )
    parser.add_argument(
        "--family",
        action="append",
        choices=["alpha101", "alpha191"],
        help="Classic alpha family to generate. Can be passed multiple times.",
    )
    parser.add_argument("--alpha101", action="store_true", help="Generate Alpha101.")
    parser.add_argument("--alpha191", action="store_true", help="Generate Alpha191.")
    parser.add_argument(
        "--raw-price-fields",
        action="store_true",
        help="Use raw OHLCV/VWAP fields instead of adjusted price fields when both exist.",
    )
    parser.add_argument(
        "--factor-dtype",
        default="float32",
        choices=["float32", "float64"],
        help="Dtype for generated Alpha101/191 columns in the output parquet.",
    )
    parser.add_argument(
        "--compression",
        default=DEFAULT_PARQUET_COMPRESSION,
        help="Parquet compression.",
    )
    parser.add_argument(
        "--compression-level",
        type=int,
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
        "--chunk-trade-dates",
        type=_positive_int,
        default=60,
        help="Number of target trade dates per factor-store partition.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate requested factor-store families even when they already exist.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print per-factor computation and factor-store partition write progress.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = run_generation(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if result.output_path is not None:
        print(f"Saved panel: {result.output_path}")
    if result.manifest_path is not None:
        print(f"Saved manifest: {result.manifest_path}")
    if result.factor_store_manifest_path is not None:
        print(f"Saved factor store: {result.factor_store_manifest_path}")
    print(f"Rows: {result.rows:,}")
    print(f"Alpha columns: {result.alpha_columns:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
