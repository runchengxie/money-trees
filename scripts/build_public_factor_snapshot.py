from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from moneytree.cli.factor_evidence import build_parser
from moneytree.cli.factor_evidence import main as factor_evidence_main


def main(argv: Sequence[str] | None = None) -> int:
    parser: argparse.ArgumentParser = build_parser()
    args = parser.parse_args(argv)
    panel = Path(args.panel).resolve()
    output = Path(args.output).resolve()
    if panel == output:
        parser.error("--output must not overwrite --panel")
    return factor_evidence_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
