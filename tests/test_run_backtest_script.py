from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def _build_smoke_dataset() -> pd.DataFrame:
    dates = pd.date_range("2004-03-31", "2015-12-31", freq="QE")
    tickers = ["AAA", "BBB", "CCC", "DDD"]
    rows: list[dict[str, object]] = []

    for dt in dates:
        quarter_sign = 1.0 if dt.quarter in {1, 3} else -1.0
        for i, ticker in enumerate(tickers):
            ticker_sign = 1.0 if i % 2 == 0 else -1.0
            rel = 0.08 * ticker_sign + 0.01 * quarter_sign
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

    run_summary = (out_dir / "run_summary.txt").read_text(encoding="utf-8")
    assert "Backtest run summary" in run_summary
    assert "Tail / Distribution" in run_summary
    assert "Segment diagnostics" in run_summary
    assert "Final Holdout OOS" in run_summary
