#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from treealpha.runner import (  # noqa: E402
    HoldoutResult,
    SegmentFitResult,
    _build_holdout_result,
    build_run_summary_text,
    combine_backtest_segments,
    legacy_main,
)


def main() -> None:
    legacy_main()


if __name__ == "__main__":
    main()
