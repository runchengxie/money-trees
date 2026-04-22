#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from treealpha.data import load_market_data, save_market_data  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert dataset pickle/parquet into parquet.")
    parser.add_argument("--input", required=True, help="Input dataset path (.pkl/.parquet).")
    parser.add_argument(
        "--output",
        default="",
        help="Output parquet path (default: input name with .parquet suffix).",
    )
    parser.add_argument("--compression", default="snappy", help="Parquet compression codec.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = (
        Path(args.output)
        if args.output
        else input_path.with_suffix(".parquet")
    )

    frame = load_market_data(input_path)
    save_market_data(frame, output_path, compression=args.compression)
    print(f"Wrote parquet: {output_path}")
    print(f"Rows: {len(frame):,}")
    print(f"Columns: {len(frame.columns):,}")


if __name__ == "__main__":
    main()
