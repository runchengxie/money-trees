from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from moneytree.data import load_market_data
from moneytree.factor_store import load_factor_store
from moneytree.factors.mining import resolve_factor_names, run_mining


def _load_panel(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    if file_path.is_file() and file_path.name == "manifest.json":
        return load_factor_store(file_path)
    return load_market_data(file_path)


def _slice(frame: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if not start and not end:
        return frame
    if "date" in frame.index.names:
        dates = pd.to_datetime(frame.index.get_level_values("date"))
    else:
        dates = pd.to_datetime(frame["date"])
    mask = pd.Series(True, index=frame.index)
    if start:
        mask &= dates >= pd.Timestamp(start)
    if end:
        mask &= dates <= pd.Timestamp(end)
    return frame.loc[mask]


def run(args: argparse.Namespace) -> int:
    panel = _load_panel(args.data)
    indexed = (
        panel.set_index(["date", "ticker"]).sort_index()
        if {"date", "ticker"}.issubset(panel.columns)
        else panel
    )

    factor_names = resolve_factor_names(
        indexed.columns,
        factor_prefixes=args.factor_prefixes,
        factor_columns=args.factor_columns,
    )

    train = _slice(indexed, args.start_date, args.end_date)
    test = _slice(indexed, args.test_start_date, args.test_end_date)

    report = run_mining(
        train,
        factor_names,
        future_return_period=args.future_return_period,
        pop_size=args.pop_size,
        max_gen=args.max_gen,
        max_depth=args.max_depth,
        seed=args.seed,
        complexity_penalty=args.complexity_penalty,
        crossover_rate=args.crossover_rate,
        mutation_rate=args.mutation_rate,
        elitism_rate=args.elitism_rate,
        tournament_size=args.tournament_size,
        test_panel=test,
        neutralize=args.neutralize,
    )

    if "error" in report:
        print(f"Error: {report['error']}", file=sys.stderr)
        return 1

    print(f"最佳因子 (训练集): {report['best_expression']}")
    print(f"训练集适应度: {report['best_fitness']:.4f}")

    validation = report.get("test")
    if validation is not None:
        print("测试集验证结果:")
        print(f"  平均IC: {validation.get('ic_mean', 0):.4f}")
        print(f"  ICIR: {validation.get('icir', 0):.4f}")
        quantiles = validation.get("quantile_returns", {})
        if isinstance(quantiles, dict):
            for group, value in sorted(quantiles.items()):
                print(f"  第 {int(group) + 1} 组: {float(value):.6f}")
        else:
            print(f"  {quantiles}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(args.data),
        "factor_terminals": factor_names,
        "train_start": args.start_date,
        "train_end": args.end_date,
        "test_start": args.test_start_date,
        "test_end": args.test_end_date,
        "future_return_period": args.future_return_period,
        "seed": args.seed,
        "neutralize": bool(args.neutralize),
        "train": {
            "best_expression": report["best_expression"],
            "best_fitness": report["best_fitness"],
        },
        "test": validation,
        "generations": report["generations"],
    }
    (output_dir / "mining_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "best_factor.txt").write_text(
        f"{report['train']['best_expression']}\n", encoding="utf-8"
    )
    print(f"报告已保存到 {output_dir / 'mining_report.json'}")
    return 0


def _positive_float(raw: str) -> float:
    value = float(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run genetic-programming factor mining over selected alpha factor terminals "
            "and report train fitness plus out-of-sample IC/ICIR/quantile returns."
        ),
    )
    parser.add_argument("--data", required=True, help="Panel parquet or factor-store manifest.json.")
    parser.add_argument(
        "--factor-prefixes",
        action="append",
        help="Factor column prefixes to use as terminals (e.g. alpha101_). Repeatable.",
    )
    parser.add_argument(
        "--factor-column",
        action="append",
        dest="factor_columns",
        help="Explicit factor column terminal names. Repeatable.",
    )
    parser.add_argument("--start-date", help="Train window start (YYYY-MM-DD or YYYYMMDD).")
    parser.add_argument("--end-date", help="Train window end (inclusive).")
    parser.add_argument("--test-start-date", help="Out-of-sample window start.")
    parser.add_argument("--test-end-date", help="Out-of-sample window end (inclusive).")
    parser.add_argument("--future-return-period", type=_positive_int, default=5)
    parser.add_argument("--pop-size", type=_positive_int, default=100)
    parser.add_argument("--max-gen", type=_positive_int, default=20)
    parser.add_argument("--max-depth", type=_positive_int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--complexity-penalty", type=_positive_float, default=0.001)
    parser.add_argument("--crossover-rate", type=float, default=0.9)
    parser.add_argument("--mutation-rate", type=float, default=0.15)
    parser.add_argument("--elitism-rate", type=float, default=0.1)
    parser.add_argument("--tournament-size", type=_positive_int, default=5)
    parser.add_argument(
        "--neutralize",
        action="store_true",
        help="Neutralize the discovered factor against market cap for quantile validation.",
    )
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
