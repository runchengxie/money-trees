#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from strategy.backtest import (  # noqa: E402
    build_rolling_windows,
    build_spy_benchmark,
    compute_performance_metrics,
    run_rolling_backtest,
)
from strategy.data import (  # noqa: E402
    build_xy_returns,
    get_feature_columns,
    load_market_data,
    preprocess_data,
    save_market_data,
    slice_by_date,
)
from strategy.model import (  # noqa: E402
    fit_random_forest,
    select_positive_importance_features,
    sequential_feature_selection,
    signal_profit,
    tune_random_forest,
)


@dataclass
class SegmentSpec:
    name: str
    train_start: str
    train_end: str
    valid_start: str
    valid_end: str
    rolling_start: str
    rolling_windows: int


@dataclass
class SegmentFitResult:
    feature_columns: list[str]
    model_params: dict[str, Any]
    validation_profit: float
    validation_active_names: int
    tuning_best_value: float
    selection_history: pd.DataFrame | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run random-forest rolling backtest.")
    parser.add_argument("--data", required=True, help="Input data file (.pkl/.parquet).")
    parser.add_argument("--output-dir", default="artifacts/backtest", help="Output directory.")
    parser.add_argument(
        "--label-source",
        choices=["actual", "pred_rel_return"],
        default="actual",
        help="Label source; 'actual' uses next_period_return - spy_next_period_return.",
    )
    parser.add_argument("--label-threshold", type=float, default=0.05)
    parser.add_argument("--add-missing-indicators", action="store_true")
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--n-trials", type=int, default=50)
    parser.add_argument(
        "--feature-selection",
        choices=["none", "importance", "sequential"],
        default="importance",
    )
    parser.add_argument("--min-features", type=int, default=2)
    parser.add_argument("--max-selection-steps", type=int, default=200)
    parser.add_argument("--random-seed", type=int, default=123)
    parser.add_argument("--train-months", type=int, default=60)
    parser.add_argument("--gap-months", type=int, default=3)
    parser.add_argument("--test-months", type=int, default=3)
    parser.add_argument("--segment1-start", default="2004-04-01")
    parser.add_argument("--segment1-windows", type=int, default=60)
    parser.add_argument("--segment2-start", default="2009-04-01")
    parser.add_argument("--segment2-windows", type=int, default=20)
    parser.add_argument(
        "--export-parquet",
        default="",
        help="Optional path to save the cleaned dataset as parquet.",
    )
    return parser.parse_args()


def fit_segment_model(
    frame: pd.DataFrame,
    spec: SegmentSpec,
    args: argparse.Namespace,
    seed_offset: int = 0,
) -> SegmentFitResult:
    train_frame = slice_by_date(frame, spec.train_start, spec.train_end)
    valid_frame = slice_by_date(frame, spec.valid_start, spec.valid_end)
    if train_frame.empty or valid_frame.empty:
        raise ValueError(f"Segment {spec.name} has empty train/valid frame.")

    feature_columns = get_feature_columns(train_frame)
    train_x, train_y, _ = build_xy_returns(train_frame, feature_columns)
    valid_x, _, valid_returns = build_xy_returns(valid_frame, feature_columns)

    seed = args.random_seed + seed_offset
    best_params, best_value = tune_random_forest(
        train_x=train_x,
        train_y=train_y,
        valid_x=valid_x,
        valid_returns=valid_returns,
        n_trials=args.n_trials,
        random_state=seed,
        cost_bps=args.cost_bps,
    )

    selected_features = feature_columns
    selection_history: pd.DataFrame | None = None
    if args.feature_selection == "importance":
        model = fit_random_forest(train_x, train_y, params=best_params, random_state=seed)
        selected_features = select_positive_importance_features(model, feature_columns)
    elif args.feature_selection == "sequential":
        selection = sequential_feature_selection(
            train_x=train_x,
            train_y=train_y,
            valid_x=valid_x,
            valid_returns=valid_returns,
            params=best_params,
            random_state=seed,
            min_features=args.min_features,
            max_steps=args.max_selection_steps,
            cost_bps=args.cost_bps,
        )
        selected_features = selection.selected_features
        selection_history = selection.history

    train_sel = train_x[selected_features]
    valid_sel = valid_x[selected_features]
    model = fit_random_forest(train_sel, train_y, params=best_params, random_state=seed)
    valid_preds = model.predict(valid_sel)
    valid_profit = signal_profit(valid_preds, valid_returns, cost_bps=args.cost_bps)
    active_names = int((valid_preds != 0).sum())

    return SegmentFitResult(
        feature_columns=selected_features,
        model_params=best_params,
        validation_profit=valid_profit,
        validation_active_names=active_names,
        tuning_best_value=best_value,
        selection_history=selection_history,
    )


def combine_backtest_segments(
    first_nav: pd.Series,
    second_nav: pd.Series,
) -> pd.Series:
    if first_nav.empty:
        return second_nav.copy()
    if second_nav.empty:
        return first_nav.copy()
    combined = pd.concat([first_nav, second_nav]).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    combined.name = "strategy_nav"
    return combined


def write_outputs(
    out_dir: Path,
    strategy_nav: pd.Series,
    spy_nav: pd.Series,
    segment_a: SegmentFitResult,
    segment_b: SegmentFitResult,
    metrics: dict[str, float],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    strategy_nav.to_frame(name="strategy_nav").to_csv(out_dir / "strategy_nav.csv")
    spy_nav.to_frame(name="spy_nav").to_csv(out_dir / "spy_nav.csv")
    pd.concat([strategy_nav, spy_nav], axis=1).to_csv(out_dir / "strategy_vs_spy.csv")

    summary = {
        "segment_a_validation_profit": segment_a.validation_profit,
        "segment_a_validation_active_names": segment_a.validation_active_names,
        "segment_a_tuning_best_value": segment_a.tuning_best_value,
        "segment_a_feature_count": len(segment_a.feature_columns),
        "segment_b_validation_profit": segment_b.validation_profit,
        "segment_b_validation_active_names": segment_b.validation_active_names,
        "segment_b_tuning_best_value": segment_b.tuning_best_value,
        "segment_b_feature_count": len(segment_b.feature_columns),
    }
    summary.update(metrics)
    (out_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    (out_dir / "segment_a_features.txt").write_text(
        "\n".join(segment_a.feature_columns), encoding="utf-8"
    )
    (out_dir / "segment_b_features.txt").write_text(
        "\n".join(segment_b.feature_columns), encoding="utf-8"
    )

    if segment_a.selection_history is not None and not segment_a.selection_history.empty:
        segment_a.selection_history.to_csv(out_dir / "segment_a_selection_history.csv", index=False)
    if segment_b.selection_history is not None and not segment_b.selection_history.empty:
        segment_b.selection_history.to_csv(out_dir / "segment_b_selection_history.csv", index=False)


def main() -> None:
    args = parse_args()

    raw = load_market_data(args.data)
    frame = preprocess_data(
        raw,
        label_source=args.label_source,
        label_threshold=args.label_threshold,
        add_missing_indicators=args.add_missing_indicators,
    )
    if args.export_parquet:
        save_market_data(frame, args.export_parquet)

    segment_a_spec = SegmentSpec(
        name="segment_a",
        train_start="2004-01-01",
        train_end="2009-01-01",
        valid_start="2009-04-01",
        valid_end="2009-07-01",
        rolling_start=args.segment1_start,
        rolling_windows=args.segment1_windows,
    )
    segment_b_spec = SegmentSpec(
        name="segment_b",
        train_start="2009-01-01",
        train_end="2014-01-01",
        valid_start="2014-04-01",
        valid_end="2014-07-01",
        rolling_start=args.segment2_start,
        rolling_windows=args.segment2_windows,
    )

    segment_a = fit_segment_model(frame=frame, spec=segment_a_spec, args=args, seed_offset=0)
    segment_b = fit_segment_model(frame=frame, spec=segment_b_spec, args=args, seed_offset=1000)

    windows_a = build_rolling_windows(
        start_date=segment_a_spec.rolling_start,
        n_windows=segment_a_spec.rolling_windows,
        train_months=args.train_months,
        gap_months=args.gap_months,
        test_months=args.test_months,
    )
    bt_a = run_rolling_backtest(
        frame=frame,
        windows=windows_a,
        feature_columns=segment_a.feature_columns,
        model_params=segment_a.model_params,
        random_state=args.random_seed,
        cost_bps=args.cost_bps,
        initial_nav=1.0,
    )

    initial_nav = float(bt_a.nav.iloc[-1]) if not bt_a.nav.empty else 1.0
    windows_b = build_rolling_windows(
        start_date=segment_b_spec.rolling_start,
        n_windows=segment_b_spec.rolling_windows,
        train_months=args.train_months,
        gap_months=args.gap_months,
        test_months=args.test_months,
    )
    bt_b = run_rolling_backtest(
        frame=frame,
        windows=windows_b,
        feature_columns=segment_b.feature_columns,
        model_params=segment_b.model_params,
        random_state=args.random_seed + 2000,
        cost_bps=args.cost_bps,
        initial_nav=initial_nav,
    )

    strategy_nav = combine_backtest_segments(bt_a.nav, bt_b.nav)
    spy_nav = build_spy_benchmark(frame, strategy_nav.index)
    metrics = compute_performance_metrics(strategy_nav, spy_nav)

    out_dir = Path(args.output_dir)
    write_outputs(out_dir, strategy_nav, spy_nav, segment_a, segment_b, metrics)

    print(f"Output directory: {out_dir}")
    print(f"Segment A feature count: {len(segment_a.feature_columns)}")
    print(f"Segment B feature count: {len(segment_b.feature_columns)}")
    if metrics:
        print(json.dumps(metrics, indent=2))
    else:
        print("No metrics were computed; verify strategy/benchmark date overlap.")


if __name__ == "__main__":
    main()

