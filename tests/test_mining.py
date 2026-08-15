from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from moneytree.cli.mining import main
from moneytree.factors.mining import (
    ExprNode,
    build_terminals,
    evaluate_expression,
    fitness_function,
    get_tree_depth,
    prepare_mining_data,
    resolve_factor_names,
    run_mining,
    tree_to_formula,
)


def _panel(days: int = 80, tickers: list[str] | None = None) -> pd.DataFrame:
    tickers = tickers or ["A", "B", "C"]
    dates = pd.date_range("2021-01-04", periods=days, freq="B")
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        for date in dates:
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "close_adj": 10.0 + tickers.index(ticker) + dates.get_loc(date) * 0.01,
                    "total_mv": 1.0e10 + tickers.index(ticker) * 1.0e9,
                    "alpha101_001": (tickers.index(ticker) + dates.get_loc(date) % 5) % 3,
                    "alpha101_002": (tickers.index(ticker) * 2 + dates.get_loc(date) % 4) % 3,
                    "alpha191_001": (tickers.index(ticker) * 3 + dates.get_loc(date) % 6) % 3,
                }
            )
    return pd.DataFrame(rows)


def test_resolve_factor_names_by_prefix_and_explicit() -> None:
    columns = ["alpha101_001", "alpha101_002", "alpha191_001", "close_adj"]

    by_prefix = resolve_factor_names(columns, factor_prefixes=["alpha101"])
    assert by_prefix == ["alpha101_001", "alpha101_002"]

    explicit = resolve_factor_names(columns, factor_columns=["alpha191_001"])
    assert explicit == ["alpha191_001"]

    all_factors = resolve_factor_names(columns)
    assert all_factors == ["alpha101_001", "alpha101_002", "alpha191_001"]

    with pytest.raises(ValueError, match="missing"):
        resolve_factor_names(columns, factor_columns=["alpha101_999"])


def test_expression_utilities() -> None:
    expr = ExprNode("+", [ExprNode("alpha101_001"), ExprNode(5)])
    assert get_tree_depth(expr) == 2
    assert tree_to_formula(expr) == "(alpha101_001 + 5)"
    assert build_terminals(["alpha101_001"])[-1][1] is True


def test_evaluate_expression_and_fitness() -> None:
    panel = _panel()
    names = resolve_factor_names(panel.columns)
    data = prepare_mining_data(panel, names, future_return_period=5)

    expr = ExprNode("cs_rank", [ExprNode("alpha101_001")])
    values = evaluate_expression(expr, data)
    assert isinstance(values, pd.DataFrame)
    assert (values.rank(axis=1, pct=True).max().max()) == pytest.approx(1.0)

    fitness = fitness_function(expr, data, complexity_penalty=0.001)
    assert isinstance(fitness, float)
    assert fitness >= 0.0

    constant_tree = ExprNode("+", [ExprNode("alpha101_001"), ExprNode(3)])
    assert fitness_function(constant_tree, data, 0.001) >= 0.0


def test_run_mining_returns_report_with_test_validation() -> None:
    panel = _panel()
    indexed = panel.set_index(["date", "ticker"]).sort_index()
    names = ["alpha101_001", "alpha101_002"]
    train = indexed.loc[: "2021-03-31"]
    test = indexed.loc["2021-04-01":]

    report = run_mining(
        train,
        names,
        future_return_period=5,
        pop_size=10,
        max_gen=2,
        max_depth=3,
        seed=1,
        test_panel=test,
    )

    assert "best_expression" in report
    assert report["terminals"] == names
    assert len(report["generations"]) == 3
    assert "test" in report
    assert "ic_mean" in report["test"]


def test_mining_cli_writes_report(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    _panel().to_parquet(panel_path)
    output_dir = tmp_path / "mining"

    rc = main(
        [
            "--data",
            str(panel_path),
            "--factor-prefixes",
            "alpha101",
            "--pop-size",
            "10",
            "--max-gen",
            "2",
            "--max-depth",
            "3",
            "--seed",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )
    assert rc == 0

    report_path = output_dir / "mining_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["train"]["best_expression"]
    assert "generations" in report
