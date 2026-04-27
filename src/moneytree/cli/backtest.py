from __future__ import annotations

import argparse

from moneytree.config import load_backtest_settings
from moneytree.runner import print_run_results, run_backtest

DEFAULT_CONFIG_PATHS = [
    "configs/market/cn.yaml",
    "configs/model/rf.yaml",
    "configs/backtest/default.yaml",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Money Trees backtest from config.")
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="Repeatable config path. Later files override earlier files.",
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
        config_paths=list(args.config) or list(DEFAULT_CONFIG_PATHS),
        data_path=args.data or None,
        output_dir=args.output_dir or None,
        overrides=list(args.overrides),
    )
    print_run_results(run_backtest(settings))


if __name__ == "__main__":
    main()
