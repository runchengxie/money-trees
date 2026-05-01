from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from moneytree._runner_holdout import HoldoutResult
from moneytree.backtest import build_notebook_report_artifacts


def _write_selection_curve(path: Path, history: pd.DataFrame | None) -> None:
    if history is None or history.empty:
        return
    curve = history.rename(
        columns={
            "n_features": "feature_count",
            "score": "validation_signal_profit",
        }
    ).copy()
    curve.to_csv(path, index=False)


def _write_notebook_report_files(
    *,
    out_dir: Path,
    strategy_nav: pd.Series,
    benchmark_nav: pd.Series,
    signal_nav: pd.Series,
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> None:
    report = build_notebook_report_artifacts(
        strategy_nav=strategy_nav,
        benchmark_nav=benchmark_nav,
        signal_nav=signal_nav,
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
    )
    report.navs.to_csv(out_dir / "notebook_report_navs.csv")
    report.rolling_beta.to_frame(name="rolling_beta").to_csv(
        out_dir / "notebook_rolling_beta.csv"
    )
    report.residual_returns.to_frame(name="residual_return").to_csv(
        out_dir / "notebook_residual_returns.csv"
    )
    report.residual_distribution.to_csv(
        out_dir / "notebook_residual_distribution.csv",
        index=False,
    )


def write_outputs(
    *,
    out_dir: Path,
    benchmark_name: str,
    strategy_nav: pd.Series,
    signal_nav: pd.Series,
    benchmark_nav: pd.Series,
    strategy_returns: pd.Series,
    signal_profit: pd.Series,
    benchmark_returns: pd.Series,
    strategy_turnover: pd.Series,
    active_names: pd.Series,
    signal_turnover: pd.Series,
    signal_active_names: pd.Series,
    period_ic: pd.Series,
    period_rank_ic: pd.Series,
    portfolio_diagnostics: pd.DataFrame,
    segment_a: Any,
    segment_b: Any,
    metrics: dict[str, float],
    run_config: dict[str, Any],
    experiment_manifest: dict[str, Any],
    run_summary_text: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    strategy_nav.to_frame(name="strategy_nav").to_csv(out_dir / "strategy_nav.csv")
    signal_nav.to_frame(name="signal_nav").to_csv(out_dir / "signal_nav.csv")
    benchmark_nav.to_frame(name="benchmark_nav").to_csv(out_dir / "benchmark_nav.csv")
    strategy_returns.to_frame(name="strategy_ret").to_csv(out_dir / "strategy_returns.csv")
    benchmark_returns.to_frame(name="benchmark_ret").to_csv(out_dir / "benchmark_returns.csv")
    pd.concat(
        [
            signal_profit.rename("signal_profit"),
            signal_turnover.rename("signal_turnover"),
            signal_active_names.rename("signal_active_names"),
        ],
        axis=1,
    ).to_csv(out_dir / "signal_profit.csv")
    strategy_turnover.to_frame(name="strategy_turnover").to_csv(
        out_dir / "strategy_turnover.csv"
    )
    active_names.to_frame(name="active_names").to_csv(out_dir / "active_names.csv")
    pd.concat([period_ic, period_rank_ic], axis=1).to_csv(out_dir / "ic_series.csv")
    pd.concat([strategy_nav, benchmark_nav], axis=1).to_csv(
        out_dir / "strategy_vs_benchmark.csv"
    )
    oos_diagnostics = pd.concat(
        [
            strategy_returns.rename("strategy_ret"),
            benchmark_returns.rename("benchmark_ret"),
            signal_profit.rename("signal_profit"),
            strategy_turnover.rename("strategy_turnover"),
            signal_turnover.rename("signal_turnover"),
            active_names.rename("active_names"),
            signal_active_names.rename("signal_active_names"),
            period_ic.rename("period_ic"),
            period_rank_ic.rename("period_rank_ic"),
        ],
        axis=1,
    )
    if not portfolio_diagnostics.empty:
        oos_diagnostics = pd.concat([oos_diagnostics, portfolio_diagnostics], axis=1)
    oos_diagnostics.to_csv(out_dir / "oos_period_diagnostics.csv")
    summary = {
        "segment_a_validation_profit": segment_a.validation_profit,
        "segment_a_validation_turnover": segment_a.validation_turnover,
        "segment_a_validation_active_names": segment_a.validation_active_names,
        "segment_a_tuning_best_value": segment_a.tuning_best_value,
        "segment_a_feature_count": len(segment_a.feature_columns),
        "segment_b_validation_profit": segment_b.validation_profit,
        "segment_b_validation_turnover": segment_b.validation_turnover,
        "segment_b_validation_active_names": segment_b.validation_active_names,
        "segment_b_tuning_best_value": segment_b.tuning_best_value,
        "segment_b_feature_count": len(segment_b.feature_columns),
    }
    summary.update(metrics)
    summary["benchmark_name"] = benchmark_name
    summary["signal_total_return"] = (
        float(signal_nav.iloc[-1] / signal_nav.iloc[0] - 1.0)
        if len(signal_nav) > 0 and float(signal_nav.iloc[0]) != 0.0
        else float("nan")
    )
    (out_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "run_config.json").write_text(json.dumps(run_config, indent=2), encoding="utf-8")
    (out_dir / "experiment_manifest.json").write_text(
        json.dumps(experiment_manifest, indent=2),
        encoding="utf-8",
    )
    (out_dir / "run_summary.txt").write_text(run_summary_text + "\n", encoding="utf-8")
    (out_dir / "segment_a_features.txt").write_text(
        "\n".join(segment_a.feature_columns),
        encoding="utf-8",
    )
    (out_dir / "segment_b_features.txt").write_text(
        "\n".join(segment_b.feature_columns),
        encoding="utf-8",
    )
    _write_notebook_report_files(
        out_dir=out_dir,
        strategy_nav=strategy_nav,
        benchmark_nav=benchmark_nav,
        signal_nav=signal_nav,
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
    )
    if segment_a.selection_history is not None and not segment_a.selection_history.empty:
        segment_a.selection_history.to_csv(out_dir / "segment_a_selection_history.csv", index=False)
        _write_selection_curve(
            out_dir / "segment_a_feature_score_curve.csv",
            segment_a.selection_history,
        )
    if segment_b.selection_history is not None and not segment_b.selection_history.empty:
        segment_b.selection_history.to_csv(out_dir / "segment_b_selection_history.csv", index=False)
        _write_selection_curve(
            out_dir / "segment_b_feature_score_curve.csv",
            segment_b.selection_history,
        )


def write_holdout_outputs(
    *,
    out_dir: Path,
    holdout: HoldoutResult,
) -> None:
    holdout_dir = out_dir / "holdout"
    holdout_dir.mkdir(parents=True, exist_ok=True)
    holdout.strategy_nav.to_frame(name="strategy_nav").to_csv(holdout_dir / "strategy_nav.csv")
    holdout.signal_nav.to_frame(name="signal_nav").to_csv(holdout_dir / "signal_nav.csv")
    holdout.benchmark_nav.to_frame(name="benchmark_nav").to_csv(
        holdout_dir / "benchmark_nav.csv"
    )
    holdout.strategy_returns.to_frame(name="strategy_ret").to_csv(
        holdout_dir / "strategy_returns.csv"
    )
    holdout.benchmark_returns.to_frame(name="benchmark_ret").to_csv(
        holdout_dir / "benchmark_returns.csv"
    )
    pd.concat(
        [
            holdout.signal_profit.rename("signal_profit"),
            holdout.signal_turnover.rename("signal_turnover"),
            holdout.signal_active_names.rename("signal_active_names"),
        ],
        axis=1,
    ).to_csv(holdout_dir / "signal_profit.csv")
    holdout.strategy_turnover.to_frame(name="strategy_turnover").to_csv(
        holdout_dir / "strategy_turnover.csv"
    )
    holdout.active_names.to_frame(name="active_names").to_csv(holdout_dir / "active_names.csv")
    pd.concat([holdout.period_ic, holdout.period_rank_ic], axis=1).to_csv(
        holdout_dir / "ic_series.csv"
    )
    pd.concat([holdout.strategy_nav, holdout.benchmark_nav], axis=1).to_csv(
        holdout_dir / "strategy_vs_benchmark.csv"
    )
    holdout_diagnostics = pd.concat(
        [
            holdout.strategy_returns.rename("strategy_ret"),
            holdout.benchmark_returns.rename("benchmark_ret"),
            holdout.signal_profit.rename("signal_profit"),
            holdout.strategy_turnover.rename("strategy_turnover"),
            holdout.signal_turnover.rename("signal_turnover"),
            holdout.active_names.rename("active_names"),
            holdout.signal_active_names.rename("signal_active_names"),
            holdout.period_ic.rename("period_ic"),
            holdout.period_rank_ic.rename("period_rank_ic"),
        ],
        axis=1,
    )
    if not holdout.portfolio_diagnostics.empty:
        holdout_diagnostics = pd.concat(
            [holdout_diagnostics, holdout.portfolio_diagnostics],
            axis=1,
        )
    holdout_diagnostics.to_csv(holdout_dir / "oos_period_diagnostics.csv")
    _write_notebook_report_files(
        out_dir=holdout_dir,
        strategy_nav=holdout.strategy_nav,
        benchmark_nav=holdout.benchmark_nav,
        signal_nav=holdout.signal_nav,
        strategy_returns=holdout.strategy_returns,
        benchmark_returns=holdout.benchmark_returns,
    )
    (holdout_dir / "metrics.json").write_text(
        json.dumps(holdout.metrics, indent=2),
        encoding="utf-8",
    )
    (holdout_dir / "holdout_config.json").write_text(
        json.dumps(
            {
                "model_segment": holdout.model_segment,
                "benchmark_name": holdout.benchmark_name,
                "train_start": holdout.train_start,
                "train_end": holdout.train_end,
                "holdout_start": holdout.holdout_start,
                "holdout_end": holdout.holdout_end,
                "model_segment_train_start": holdout.model_segment_train_start,
                "model_segment_train_end": holdout.model_segment_train_end,
                "model_segment_valid_start": holdout.model_segment_valid_start,
                "model_segment_valid_end": holdout.model_segment_valid_end,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
