from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a pickled DataFrame to parquet.")
    parser.add_argument("--input", required=True, help="Path to the input pickle file.")
    parser.add_argument(
        "--output",
        default="",
        help="Optional output parquet path. Defaults to the input path with a .parquet suffix.",
    )
    return parser.parse_args()


def resolve_output_path(input_path: Path, output_path: str) -> Path:
    if output_path:
        return Path(output_path)
    return input_path.with_suffix(".parquet")


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = resolve_output_path(input_path, args.output)

    frame = pd.read_pickle(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output_path, index=False)

    print(
        "Compatibility notice: scripts/convert_pickle_to_parquet.py is deprecated; "
        "prefer `moneytrees-parquet-rewrite` for new migrations."
    )
    print(f"Wrote: {output_path}")
    print(f"Rows: {len(frame)}")
    print(f"Columns: {len(frame.columns)}")


if __name__ == "__main__":
    main()
