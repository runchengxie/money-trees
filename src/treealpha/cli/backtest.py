from __future__ import annotations

import argparse
from pathlib import Path

from treealpha.config import load_backtest_settings
from treealpha.runner import print_run_results, run_backtest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a treealpha backtest from config.")
    parser.add_argument(
        "--config",
        default="configs/reference_us_random_forest.toml",
        help="Path to the structured run config.",
    )
    parser.add_argument("--data", default="", help="Optional dataset override.")
    parser.add_argument("--output-dir", default="", help="Optional output directory override.")
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        help="Optional dotted.path=value override. Repeatable.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = load_backtest_settings(
        config_path=args.config,
        data_path=args.data or None,
        output_dir=args.output_dir or None,
        overrides=list(args.overrides),
    )
    print_run_results(run_backtest(settings))


if __name__ == "__main__":
    main()
