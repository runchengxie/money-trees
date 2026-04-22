from __future__ import annotations

import json
import os
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
        for idx, ticker in enumerate(tickers):
            ticker_sign = 1.0 if idx % 2 == 0 else -1.0
            rel = 0.08 * ticker_sign + 0.01 * quarter_sign
            rows.append(
                {
                    "date": dt,
                    "ticker": ticker,
                    "f_signal": rel,
                    "f_rank": float(idx),
                    "next_period_return": rel,
                    "spy_next_period_return": 0.0,
                    "spy_cum_ret": 100.0 + 0.5 * len(rows),
                }
            )
    return pd.DataFrame(rows)


def test_template_smoke_config_stack_runs(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "template_smoke.parquet"
    out_dir = tmp_path / "template_smoke_output"
    _build_smoke_dataset().to_parquet(data_path, index=False)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    config_paths = [
        "configs/market/us.yaml",
        "configs/model/rf.yaml",
        "configs/backtest/smoke.yaml",
    ]
    cmd = [sys.executable, "-m", "treealpha.cli.backtest"]
    for config_path in config_paths:
        cmd.extend(["--config", config_path])
    cmd.extend(["--data", str(data_path), "--output-dir", str(out_dir)])

    subprocess.run(cmd, cwd=root, env=env, check=True)

    run_config = json.loads((out_dir / "run_config.json").read_text(encoding="utf-8"))
    assert run_config["arguments"]["config_paths"] == config_paths
    assert run_config["holdout"]["enabled"] is True
    assert (out_dir / "metrics.json").exists()
    assert (out_dir / "benchmark_nav.csv").exists()
    assert (out_dir / "benchmark_returns.csv").exists()
    assert (out_dir / "holdout/metrics.json").exists()
    assert (out_dir / "holdout/benchmark_nav.csv").exists()
