from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from treealpha.runner import (
    HoldoutResult,
    _build_holdout_result,
    SegmentFitResult,
    build_run_summary_text,
    combine_backtest_segments,
)
from treealpha.portfolio import PortfolioConfig


def _build_smoke_dataset(freq: str = "QE") -> pd.DataFrame:
    start = "2004-03-31" if freq == "QE" else "2004-01-31"
    dates = pd.date_range(start, "2015-12-31", freq=freq)
    tickers = ["AAA", "BBB", "CCC", "DDD"]
    rows: list[dict[str, object]] = []

    for dt in dates:
        month_sign = 1.0 if dt.month % 2 == 1 else -1.0
        quarter_sign = 1.0 if dt.quarter in {1, 3} else -1.0
        for i, ticker in enumerate(tickers):
            ticker_sign = 1.0 if i % 2 == 0 else -1.0
            rel = 0.08 * ticker_sign + 0.01 * quarter_sign + 0.005 * month_sign
            rows.append(
                {
                    "date": dt,
                    "ticker": ticker,
                    "f_signal": rel,
                    "f_rank": float(i),
                    "next_period_return": rel,
                    "spy_next_period_return": 0.0,
                    "spy_cum_ret": 100.0 + 0.8 * len(rows),
                }
            )
    return pd.DataFrame(rows)


def test_run_backtest_script_smoke(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "smoke.parquet"
    out_dir = tmp_path / "artifacts"
    _build_smoke_dataset().to_parquet(data_path, index=False)

    subprocess.run(
        [
            sys.executable,
            "scripts/run_backtest.py",
            "--data",
            str(data_path),
            "--output-dir",
            str(out_dir),
            "--feature-selection",
            "importance",
            "--n-trials",
            "1",
            "--tuning-cv-folds",
            "3",
            "--segment1-windows",
            "1",
            "--segment2-windows",
            "1",
            "--holdout-start",
            "2015-01-01",
            "--holdout-end",
            "2015-12-31",
            "--holdout-model-segment",
            "segment_b",
            "--cost-bps",
            "10",
        ],
        cwd=root,
        check=True,
    )

    required = [
        "strategy_nav.csv",
        "spy_nav.csv",
        "strategy_returns.csv",
        "spy_returns.csv",
        "strategy_turnover.csv",
        "active_names.csv",
        "ic_series.csv",
        "oos_period_diagnostics.csv",
        "strategy_vs_spy.csv",
        "metrics.json",
        "run_config.json",
        "run_summary.txt",
        "segment_a_features.txt",
        "segment_b_features.txt",
    ]
    for rel_path in required:
        assert (out_dir / rel_path).exists(), rel_path

    holdout_required = [
        "holdout/strategy_nav.csv",
        "holdout/spy_nav.csv",
        "holdout/strategy_returns.csv",
        "holdout/spy_returns.csv",
        "holdout/strategy_turnover.csv",
        "holdout/active_names.csv",
        "holdout/ic_series.csv",
        "holdout/oos_period_diagnostics.csv",
        "holdout/strategy_vs_spy.csv",
        "holdout/metrics.json",
        "holdout/holdout_config.json",
    ]
    for rel_path in holdout_required:
        assert (out_dir / rel_path).exists(), rel_path

    config = json.loads((out_dir / "run_config.json").read_text(encoding="utf-8"))
    assert "arguments" in config
    assert "segment_specs" in config
    assert "holdout" in config
    assert config["holdout"]["enabled"] is True
    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    assert "strategy_annualized_return" in metrics
    assert "strategy_max_drawdown" in metrics
    assert "avg_turnover_per_period" in metrics
    if np.isfinite(metrics["tracking_error_annualized"]) and metrics["tracking_error_annualized"] != 0:
        expected_ir = (
            metrics["avg_excess_return_per_period"] * 4.0 / metrics["tracking_error_annualized"]
        )
        assert np.isclose(metrics["information_ratio"], expected_ir)

    holdout_metrics = json.loads((out_dir / "holdout/metrics.json").read_text(encoding="utf-8"))
    if (
        np.isfinite(holdout_metrics["tracking_error_annualized"])
        and holdout_metrics["tracking_error_annualized"] != 0
    ):
        expected_holdout_ir = (
            holdout_metrics["avg_excess_return_per_period"]
            * 4.0
            / holdout_metrics["tracking_error_annualized"]
        )
        assert np.isclose(holdout_metrics["information_ratio"], expected_holdout_ir)

    run_summary = (out_dir / "run_summary.txt").read_text(encoding="utf-8")
    assert "Backtest run summary" in run_summary
    assert "Tail / Distribution" in run_summary
    assert "Segment diagnostics" in run_summary
    assert "Final Holdout OOS" in run_summary


def test_treealpha_package_cli_smoke(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "smoke_cli.parquet"
    out_dir = tmp_path / "artifacts_cli"
    _build_smoke_dataset().to_parquet(data_path, index=False)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "treealpha.cli.backtest",
            "--config",
            "configs/reference_us_random_forest.toml",
            "--data",
            str(data_path),
            "--output-dir",
            str(out_dir),
            "--set",
            "model.n_trials=1",
            "--set",
            "model.tuning_cv_folds=3",
            "--set",
            "backtest.segment1_windows=1",
            "--set",
            "backtest.segment2_windows=1",
            "--set",
            "backtest.holdout.start=2015-01-01",
            "--set",
            "backtest.holdout.end=2015-12-31",
            "--set",
            "backtest.holdout.model_segment=segment_b",
        ],
        cwd=root,
        env=env,
        check=True,
    )

    assert (out_dir / "metrics.json").exists()
    assert (out_dir / "run_config.json").exists()
    assert (out_dir / "run_summary.txt").exists()
    assert (out_dir / "holdout/metrics.json").exists()


def test_run_backtest_script_holdout_uses_test_month_buckets(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "smoke_monthly.parquet"
    out_dir = tmp_path / "artifacts_monthly"
    _build_smoke_dataset(freq="ME").to_parquet(data_path, index=False)

    subprocess.run(
        [
            sys.executable,
            "scripts/run_backtest.py",
            "--data",
            str(data_path),
            "--output-dir",
            str(out_dir),
            "--feature-selection",
            "none",
            "--n-trials",
            "1",
            "--segment1-windows",
            "0",
            "--segment2-windows",
            "0",
            "--test-months",
            "3",
            "--holdout-start",
            "2015-01-01",
            "--holdout-end",
            "2015-12-31",
            "--holdout-model-segment",
            "segment_b",
            "--cost-bps",
            "10",
        ],
        cwd=root,
        check=True,
    )

    config = json.loads((out_dir / "run_config.json").read_text(encoding="utf-8"))
    assert config["holdout"]["enabled"] is True
    assert config["holdout"]["n_periods"] == 4

    holdout_returns = pd.read_csv(out_dir / "holdout/strategy_returns.csv")
    assert len(holdout_returns) == 4


def test_combine_backtest_segments_uses_last_value_on_duplicate_dates() -> None:
    first = pd.Series(
        [1.0, 1.1],
        index=pd.to_datetime(["2021-03-31", "2021-06-30"]),
        name="strategy_nav",
    )
    second = pd.Series(
        [9.9, 1.2],
        index=pd.to_datetime(["2021-06-30", "2021-09-30"]),
        name="strategy_nav",
    )

    out = combine_backtest_segments(first, second, name="strategy_nav")

    assert list(out.index) == list(pd.to_datetime(["2021-03-31", "2021-06-30", "2021-09-30"]))
    assert np.isclose(float(out.loc[pd.Timestamp("2021-06-30")]), 9.9)


def _segment_stub() -> SegmentFitResult:
    return SegmentFitResult(
        feature_columns=["f1", "f2"],
        model_params={"n_estimators": 10},
        validation_profit=0.01,
        validation_turnover=0.5,
        validation_active_names=5,
        tuning_best_value=0.02,
        selection_history=None,
    )


def _holdout_stub(start: str, end: str) -> HoldoutResult:
    idx = pd.to_datetime(["2022-03-31", "2022-06-30"])
    return HoldoutResult(
        model_segment="segment_b",
        train_start="2019-01-01",
        train_end="2021-12-31",
        holdout_start=start,
        holdout_end=end,
        strategy_nav=pd.Series([1.1, 1.2], index=idx, name="strategy_nav"),
        spy_nav=pd.Series([1.0, 1.01], index=idx, name="spy_nav"),
        strategy_returns=pd.Series([0.1, 0.09], index=idx, name="strategy_ret"),
        spy_returns=pd.Series([0.0, 0.01], index=idx, name="spy_ret"),
        strategy_turnover=pd.Series([0.5, 0.6], index=idx, name="strategy_turnover"),
        active_names=pd.Series([10, 12], index=idx, name="active_names"),
        period_ic=pd.Series([0.1, 0.2], index=idx, name="period_ic"),
        period_rank_ic=pd.Series([0.05, 0.15], index=idx, name="period_rank_ic"),
        metrics={"strategy_total_return": 0.1, "spy_total_return": 0.01},
    )


@pytest.mark.parametrize(
    ("holdout_span", "expected_note"),
    [
        (
            ("2021-01-01", "2021-12-31"),
            "holdout window overlaps the main backtest window.",
        ),
        (
            ("2023-01-01", "2023-12-31"),
            "no overlap with main backtest window.",
        ),
    ],
)
def test_build_run_summary_text_reports_holdout_overlap_note(
    holdout_span: tuple[str, str],
    expected_note: str,
) -> None:
    strategy_nav = pd.Series(
        [1.0, 1.1],
        index=pd.to_datetime(["2021-03-31", "2021-06-30"]),
        name="strategy_nav",
    )
    idx = strategy_nav.index
    run_summary = build_run_summary_text(
        strategy_nav=strategy_nav,
        strategy_turnover=pd.Series([0.2, 0.3], index=idx, name="strategy_turnover"),
        period_ic=pd.Series([0.1, np.nan], index=idx, name="period_ic"),
        period_rank_ic=pd.Series([0.05, np.nan], index=idx, name="period_rank_ic"),
        segment_a=_segment_stub(),
        segment_b=_segment_stub(),
        metrics={"strategy_total_return": 0.1, "spy_total_return": 0.05},
        tuning_cv_folds=1,
        holdout_result=_holdout_stub(*holdout_span),
    )

    assert f"Holdout overlap note: {expected_note}" in run_summary


def test_run_backtest_script_rejects_unpaired_holdout_dates(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "ignored.parquet"
    data_path.write_text("", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_backtest.py",
            "--data",
            str(data_path),
            "--holdout-start",
            "2024-01-01",
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Use --holdout-start and --holdout-end together." in result.stderr


def test_run_backtest_script_rejects_test_months_below_one(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "ignored.parquet"
    data_path.write_text("", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_backtest.py",
            "--data",
            str(data_path),
            "--test-months",
            "0",
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "--test-months must be >= 1." in result.stderr


def test_run_backtest_script_rejects_negative_feature_lag(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "ignored.parquet"
    data_path.write_text("", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_backtest.py",
            "--data",
            str(data_path),
            "--feature-lag-periods",
            "-1",
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "--feature-lag-periods must be >= 0." in result.stderr


def test_build_holdout_result_rejects_inverted_holdout_span() -> None:
    with pytest.raises(ValueError, match="--holdout-start must be <= --holdout-end."):
        _build_holdout_result(
            frame=pd.DataFrame(),
            holdout_start="2024-02-01",
            holdout_end="2024-01-01",
            model_segment="segment_b",
            segment_fit=_segment_stub(),
            args=argparse.Namespace(),
            portfolio_cfg=PortfolioConfig(),
        )
