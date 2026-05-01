from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from moneytree._runner_holdout import (
    HoldoutResult,
    _build_holdout_result,
    _periods_per_year_from_test_months,
)
from moneytree._runner_outputs import write_holdout_outputs, write_outputs
from moneytree._runner_summary import build_run_summary_text
from moneytree.backtest import (
    build_benchmark_nav,
    build_rolling_windows,
    compute_performance_metrics,
    run_rolling_backtest,
)
from moneytree.config import BacktestSettings
from moneytree.data import (
    apply_feature_lag,
    build_xy_target_returns,
    fill_feature_missing_with_reference,
    filter_factor_columns,
    get_feature_columns,
    load_market_data,
    preprocess_data,
    save_market_data,
    slice_by_date,
)
from moneytree.factor_store import estimate_factor_store_load_memory, load_factor_store
from moneytree.markets import get_market_profile
from moneytree.metadata import (
    OUTPUT_SCHEMA_VERSION,
    build_experiment_manifest,
    stable_json_hash,
)
from moneytree.models import get_model_adapter
from moneytree.portfolio import (
    PortfolioConfig,
    build_portfolio_weights,
    compute_period_return_from_weights,
)
from moneytree.resources import available_memory_bytes, ensure_memory_available, format_bytes

ROOT = Path(__file__).resolve().parents[2]


def _is_factor_store_manifest(path: str | Path) -> bool:
    file_path = Path(path)
    if file_path.suffix.lower() != ".json" or not file_path.exists():
        return False
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return payload.get("kind") == "moneytree_factor_store"


@dataclass(frozen=True)
class BacktestLoadPlan:
    mode: str
    date_start: str | None
    date_end: str | None
    requested_start: str | None
    requested_end: str | None
    warmup_days: int


def _collect_backtest_date_spans(settings: BacktestSettings) -> list[tuple[str, str]]:
    spans = [
        (settings.segment_a_train_start, settings.segment_a_train_end),
        (settings.segment_a_valid_start, settings.segment_a_valid_end),
        (settings.segment_b_train_start, settings.segment_b_train_end),
        (settings.segment_b_valid_start, settings.segment_b_valid_end),
    ]
    spans.extend(
        (train_start, train_end)
        for train_start, train_end, _, _ in build_rolling_windows(
            start_date=settings.segment1_start,
            n_windows=settings.segment1_windows,
            train_months=settings.train_months,
            gap_months=settings.gap_months,
            test_months=settings.test_months,
        )
    )
    spans.extend(
        (test_start, test_end)
        for _, _, test_start, test_end in build_rolling_windows(
            start_date=settings.segment1_start,
            n_windows=settings.segment1_windows,
            train_months=settings.train_months,
            gap_months=settings.gap_months,
            test_months=settings.test_months,
        )
    )
    spans.extend(
        (train_start, train_end)
        for train_start, train_end, _, _ in build_rolling_windows(
            start_date=settings.segment2_start,
            n_windows=settings.segment2_windows,
            train_months=settings.train_months,
            gap_months=settings.gap_months,
            test_months=settings.test_months,
        )
    )
    spans.extend(
        (test_start, test_end)
        for _, _, test_start, test_end in build_rolling_windows(
            start_date=settings.segment2_start,
            n_windows=settings.segment2_windows,
            train_months=settings.train_months,
            gap_months=settings.gap_months,
            test_months=settings.test_months,
        )
    )
    if settings.holdout_start and settings.holdout_end:
        spans.append((settings.holdout_start, settings.holdout_end))
    return [(start, end) for start, end in spans if start and end]


def _build_backtest_load_plan(settings: BacktestSettings) -> BacktestLoadPlan:
    mode = str(settings.load_mode).strip().lower()
    if mode == "full":
        return BacktestLoadPlan(
            mode=mode,
            date_start=None,
            date_end=None,
            requested_start=None,
            requested_end=None,
            warmup_days=0,
        )

    spans = _collect_backtest_date_spans(settings)
    if not spans:
        return BacktestLoadPlan(
            mode=mode,
            date_start=None,
            date_end=None,
            requested_start=None,
            requested_end=None,
            warmup_days=int(settings.load_warmup_days),
        )
    starts = [pd.Timestamp(start) for start, _ in spans]
    ends = [pd.Timestamp(end) for _, end in spans]
    requested_start = min(starts)
    requested_end = max(ends)
    warmup_days = int(settings.load_warmup_days)
    date_start = requested_start - pd.DateOffset(days=warmup_days)
    return BacktestLoadPlan(
        mode=mode,
        date_start=date_start.date().isoformat(),
        date_end=requested_end.date().isoformat(),
        requested_start=requested_start.date().isoformat(),
        requested_end=requested_end.date().isoformat(),
        warmup_days=warmup_days,
    )


def _available_backtest_memory_bytes(settings: BacktestSettings) -> tuple[int | None, float]:
    if settings.memory_budget_gb > 0:
        return int(float(settings.memory_budget_gb) * 1024**3), 1.0
    return available_memory_bytes(), float(settings.memory_budget_fraction)


def _run_factor_store_load_preflight(
    settings: BacktestSettings,
    plan: BacktestLoadPlan,
) -> dict[str, Any]:
    estimate = estimate_factor_store_load_memory(
        settings.data,
        include_factor_prefixes=settings.include_factor_prefixes,
        date_start=plan.date_start,
        date_end=plan.date_end,
    )
    available, budget_fraction = _available_backtest_memory_bytes(settings)
    ensure_memory_available(
        required_bytes=estimate.required_bytes,
        available_bytes=available,
        budget_fraction=budget_fraction,
        context="Backtest input memory preflight failed",
        detail=(
            f"rows={estimate.rows}, columns={estimate.columns}, "
            f"families={list(estimate.selected_families)}, load_mode={plan.mode}"
        ),
        remediation=(
            "Reduce selected factors with features.include_factor_families or "
            "features.include_factor_prefixes, keep backtest.load_mode=auto/date_range, "
            "shorten the backtest date span, or use a larger-memory host."
        ),
    )
    return {
        "estimated_rows": estimate.rows,
        "estimated_columns": estimate.columns,
        "estimated_required_bytes": estimate.required_bytes,
        "estimated_required": format_bytes(estimate.required_bytes),
        "memory_available_bytes": available,
        "memory_available": format_bytes(available),
        "memory_budget_fraction": budget_fraction,
        "selected_families": list(estimate.selected_families),
    }


def _load_backtest_data(settings: BacktestSettings) -> pd.DataFrame:
    plan = _build_backtest_load_plan(settings)
    load_info: dict[str, Any] = {
        "mode": plan.mode,
        "date_start": plan.date_start,
        "date_end": plan.date_end,
        "requested_start": plan.requested_start,
        "requested_end": plan.requested_end,
        "warmup_days": plan.warmup_days,
    }
    if _is_factor_store_manifest(settings.data):
        load_info["source"] = "factor_store"
        load_info["preflight"] = _run_factor_store_load_preflight(settings, plan)
        frame = load_factor_store(
            settings.data,
            include_factor_prefixes=settings.include_factor_prefixes,
            date_start=plan.date_start,
            date_end=plan.date_end,
        )
        if settings.exclude_factor_prefixes or settings.exclude_factor_columns:
            selected, summary = filter_factor_columns(
                frame.columns,
                include_factor_prefixes=settings.include_factor_prefixes,
                exclude_factor_prefixes=settings.exclude_factor_prefixes,
                exclude_factor_columns=settings.exclude_factor_columns,
            )
            frame = frame.loc[:, selected]
        else:
            summary = {
                "include_factor_prefixes": list(settings.include_factor_prefixes),
                "exclude_factor_prefixes": [],
                "exclude_factor_columns": [],
                "column_pruned": True,
            }
        summary["source"] = "factor_store"
        summary["manifest"] = str(settings.data)
        summary["load"] = load_info
        frame.attrs["factor_selection"] = summary
        frame.attrs["backtest_load"] = load_info
        return frame
    frame = load_market_data(
        settings.data,
        include_factor_prefixes=settings.include_factor_prefixes,
        exclude_factor_prefixes=settings.exclude_factor_prefixes,
        exclude_factor_columns=settings.exclude_factor_columns,
        date_start=plan.date_start,
        date_end=plan.date_end,
    )
    load_info["source"] = "market_data"
    frame.attrs["backtest_load"] = load_info
    return frame


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
    model_id: str
    train_start: str
    train_end: str
    valid_start: str
    valid_end: str
    validation_profit: float
    validation_turnover: float
    validation_active_names: int
    tuning_best_value: float
    tuning_enabled: bool
    selection_history: pd.DataFrame | None


def build_portfolio_config(settings: BacktestSettings) -> PortfolioConfig:
    return PortfolioConfig(
        min_score=float(settings.portfolio_min_score),
        winsor_z=float(settings.portfolio_winsor_z),
        use_prob_signal=True,
        weighting_method=str(settings.portfolio_weighting_method),
        gross_target=float(settings.portfolio_gross_target),
        net_target=float(settings.portfolio_net_target),
        max_name_weight=float(settings.portfolio_max_name_weight),
        min_names_per_side=int(settings.portfolio_min_names_per_side),
        use_vol_scaling=settings.portfolio_vol_scaling == "on",
        vol_power=float(settings.portfolio_vol_power),
        qp_risk_aversion=float(settings.portfolio_qp_risk_aversion),
        qp_turnover_penalty=float(settings.portfolio_qp_turnover_penalty),
        qp_cov_lookback=int(settings.portfolio_qp_cov_lookback),
        qp_cov_shrinkage=settings.portfolio_qp_cov_shrinkage == "on",
        qp_cov_ridge=float(settings.portfolio_qp_cov_ridge),
        qp_mu_clip=float(settings.portfolio_qp_mu_clip),
        qp_max_names=int(settings.portfolio_qp_max_names),
        qp_solver_max_iter=int(settings.portfolio_qp_solver_max_iter),
        qp_solver_ftol=float(settings.portfolio_qp_solver_ftol),
        qp_fallback_to_heuristic=settings.portfolio_qp_fallback_to_heuristic == "on",
        sector_neutral=settings.portfolio_sector_neutral == "on",
        sector_prefix=str(settings.portfolio_sector_prefix),
    )


def _extra_feature_drop(settings: BacktestSettings) -> set[str]:
    return {str(column) for column in settings.market_tradability_columns.values()}


def fit_segment_model(
    *,
    frame: pd.DataFrame,
    spec: SegmentSpec,
    settings: BacktestSettings,
    portfolio_cfg: PortfolioConfig,
    model_adapter,
    market_profile,
    seed_offset: int = 0,
) -> SegmentFitResult:
    train_raw = market_profile.filter_tradable_frame(
        slice_by_date(frame, spec.train_start, spec.train_end),
        settings=settings,
    )
    valid_raw = market_profile.filter_tradable_frame(
        slice_by_date(frame, spec.valid_start, spec.valid_end),
        settings=settings,
    )
    if train_raw.empty or valid_raw.empty:
        raise ValueError(f"Segment {spec.name} has empty train/valid frame.")

    train_frame = fill_feature_missing_with_reference(
        frame=train_raw,
        reference=train_raw,
        add_missing_indicators=settings.add_missing_indicators,
    )
    valid_frame = fill_feature_missing_with_reference(
        frame=valid_raw,
        reference=train_raw,
        add_missing_indicators=settings.add_missing_indicators,
    )

    feature_columns = get_feature_columns(train_frame, extra_drop=_extra_feature_drop(settings))
    train_x, train_y, train_returns = build_xy_target_returns(
        train_frame,
        feature_columns,
        target_column=model_adapter.training_target_column,
    )
    valid_x, _, valid_returns = build_xy_target_returns(
        valid_frame,
        feature_columns,
        target_column=model_adapter.training_target_column,
    )

    seed = settings.random_seed + seed_offset
    prepared = model_adapter.prepare_training(
        train_x=train_x,
        train_y=train_y,
        train_returns=train_returns,
        valid_x=valid_x,
        valid_returns=valid_returns,
        feature_selection=settings.feature_selection,
        n_trials=settings.n_trials,
        random_state=seed,
        cost_bps=settings.cost_bps,
        tuning_cv_folds=settings.tuning_cv_folds,
        min_features=settings.min_features,
        max_steps=settings.max_selection_steps,
        base_params=settings.model_params,
    )
    selected_features = list(prepared.selected_features)

    train_sel = train_x[selected_features]
    valid_sel = valid_x[selected_features]
    model = model_adapter.fit(
        train_x=train_sel,
        train_y=train_y,
        params=prepared.model_params,
        random_state=seed,
    )
    outputs = model_adapter.predict_outputs(model=model, features=valid_sel)
    valid_weights = build_portfolio_weights(
        predictions=outputs.predictions
        if outputs.predictions is not None
        else np.zeros(len(valid_sel), dtype=int),
        probs=outputs.probabilities,
        classes_=outputs.classes_,
        raw_scores=outputs.scores,
        sample_index=valid_sel.index,
        train_frame=train_frame,
        test_frame=valid_frame,
        cfg=portfolio_cfg,
        previous_weights=None,
    )
    valid_profit, _, valid_turnover = compute_period_return_from_weights(
        weights=valid_weights,
        realized_returns=valid_returns,
        sample_index=valid_sel.index,
        cost_bps=settings.cost_bps,
        previous_weights=None,
    )
    return SegmentFitResult(
        feature_columns=selected_features,
        model_params=prepared.model_params,
        model_id=model_adapter.model_id,
        train_start=spec.train_start,
        train_end=spec.train_end,
        valid_start=spec.valid_start,
        valid_end=spec.valid_end,
        validation_profit=valid_profit,
        validation_turnover=valid_turnover,
        validation_active_names=int(len(valid_weights)),
        tuning_best_value=prepared.tuning_best_value,
        tuning_enabled=bool(settings.n_trials > 0 or settings.tuning_cv_folds > 1),
        selection_history=prepared.selection_history,
    )


def combine_backtest_segments(first_series: pd.Series, second_series: pd.Series, name: str) -> pd.Series:
    if first_series.empty:
        out = second_series.copy()
        out.name = name
        return out
    if second_series.empty:
        out = first_series.copy()
        out.name = name
        return out
    combined = pd.concat([first_series, second_series]).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    combined.name = name
    return combined



def resolve_git_commit(root: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    commit = out.strip()
    return commit or None


def build_run_config(
    *,
    settings: BacktestSettings,
    segment_a_spec: SegmentSpec,
    segment_b_spec: SegmentSpec,
    segment_a: SegmentFitResult | None = None,
    segment_b: SegmentFitResult | None = None,
    experiment_manifest: dict[str, Any] | None = None,
    holdout_result: HoldoutResult | None = None,
    factor_load_info: dict[str, Any] | None = None,
    input_load_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_at_utc = (
        str(experiment_manifest["run"]["resolved_at_utc"])
        if experiment_manifest is not None
        else datetime.now(timezone.utc).isoformat()
    )
    git_commit = (
        experiment_manifest["run"]["git_commit"]
        if experiment_manifest is not None
        else resolve_git_commit(ROOT)
    )
    config: dict[str, Any] = {
        "resolved_at_utc": resolved_at_utc,
        "git_commit": git_commit,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "arguments": settings.to_display_config(),
        "benchmark": {
            "name": settings.benchmark_name,
            "return_column": settings.benchmark_return_column,
            "cum_column": settings.benchmark_cum_column,
            "cum_mode": settings.benchmark_cum_mode,
        },
        "segment_specs": {
            "segment_a": asdict(segment_a_spec),
            "segment_b": asdict(segment_b_spec),
        },
        "factor_selection": {
            "include_factor_prefixes": list(settings.include_factor_prefixes),
            "exclude_factor_prefixes": list(settings.exclude_factor_prefixes),
            "exclude_factor_columns": list(settings.exclude_factor_columns),
            **(factor_load_info or {}),
        },
        "input_load": input_load_info or {},
    }
    if segment_a is not None and segment_b is not None:
        config["segment_fits"] = {
            "segment_a": {
                "model_id": segment_a.model_id,
                "train_start": segment_a.train_start,
                "train_end": segment_a.train_end,
                "valid_start": segment_a.valid_start,
                "valid_end": segment_a.valid_end,
                "selected_feature_count": len(segment_a.feature_columns),
                "tuning_enabled": segment_a.tuning_enabled,
                "tuning_best_value": segment_a.tuning_best_value,
            },
            "segment_b": {
                "model_id": segment_b.model_id,
                "train_start": segment_b.train_start,
                "train_end": segment_b.train_end,
                "valid_start": segment_b.valid_start,
                "valid_end": segment_b.valid_end,
                "selected_feature_count": len(segment_b.feature_columns),
                "tuning_enabled": segment_b.tuning_enabled,
                "tuning_best_value": segment_b.tuning_best_value,
            },
        }
    if experiment_manifest is not None:
        config["reproducibility"] = {
            "dataset_version": experiment_manifest["dataset"]["dataset_version"],
            "input_data_sha256": experiment_manifest["input_data"]["sha256"],
            "raw_input_schema_hash": experiment_manifest["schemas"]["raw_input"]["schema_hash"],
            "model_frame_schema_hash": experiment_manifest["schemas"]["model_frame"]["schema_hash"],
            "config_files_hash": experiment_manifest["config"]["files_hash"],
            "resolved_config_hash": experiment_manifest["config"]["resolved_config_hash"],
            "experiment_manifest_path": "experiment_manifest.json",
            "experiment_manifest_hash": stable_json_hash(experiment_manifest),
        }
    if holdout_result is not None:
        config["holdout"] = {
            "enabled": True,
            "model_segment": holdout_result.model_segment,
            "train_start": holdout_result.train_start,
            "train_end": holdout_result.train_end,
            "holdout_start": holdout_result.holdout_start,
            "holdout_end": holdout_result.holdout_end,
            "n_periods": int(len(holdout_result.strategy_returns)),
        }
    else:
        config["holdout"] = {"enabled": False}
    return config


def run_backtest(settings: BacktestSettings) -> dict[str, Any]:
    if settings.tuning_cv_folds < 1:
        raise ValueError("--tuning-cv-folds must be >= 1.")
    if settings.test_months < 1:
        raise ValueError("--test-months must be >= 1.")
    if settings.feature_lag_periods < 0:
        raise ValueError("--feature-lag-periods must be >= 0.")
    if str(settings.load_mode).strip().lower() not in {"auto", "date_range", "full"}:
        raise ValueError("--load-mode must be 'auto', 'date_range', or 'full'.")
    if settings.load_warmup_days < 0:
        raise ValueError("--load-warmup-days must be >= 0.")
    if settings.memory_budget_gb < 0:
        raise ValueError("--memory-budget-gb must be >= 0.")
    if not 0 < settings.memory_budget_fraction <= 1:
        raise ValueError("--memory-budget-fraction must be > 0 and <= 1.")
    if settings.portfolio_qp_cov_lookback < 1:
        raise ValueError("--portfolio-qp-cov-lookback must be >= 1.")
    if settings.portfolio_qp_max_names < 0:
        raise ValueError("--portfolio-qp-max-names must be >= 0.")
    if bool(settings.holdout_start) != bool(settings.holdout_end):
        raise ValueError("Use --holdout-start and --holdout-end together.")
    if settings.benchmark_cum_mode not in {"nav", "cumulative_return"}:
        raise ValueError("--benchmark-cum-mode must be 'nav' or 'cumulative_return'.")
    if settings.missing_feature_policy not in {"error", "warn_fill_zero", "fill_zero"}:
        raise ValueError(
            "--missing-feature-policy must be 'error', 'warn_fill_zero', or 'fill_zero'."
        )

    model_adapter = get_model_adapter(settings.model_id)
    model_adapter.validate_configuration(
        feature_selection=settings.feature_selection,
        n_trials=settings.n_trials,
    )
    market_profile = get_market_profile(settings.market_profile)
    portfolio_cfg = build_portfolio_config(settings)

    raw = _load_backtest_data(settings)
    factor_load_info = dict(raw.attrs.get("factor_selection", {}))
    input_load_info = dict(raw.attrs.get("backtest_load", {}))
    frame = preprocess_data(
        raw,
        market_profile=market_profile,
        label_source=settings.label_source,
        label_threshold=settings.label_threshold,
        add_missing_indicators=False,
        apply_global_fill=False,
        settings=settings,
    )
    if settings.feature_lag_periods > 0:
        frame = apply_feature_lag(
            frame,
            feature_columns=get_feature_columns(frame, extra_drop=_extra_feature_drop(settings)),
            lag_periods=int(settings.feature_lag_periods),
        )

    if settings.export_parquet:
        export_frame = preprocess_data(
            raw,
            market_profile=market_profile,
            label_source=settings.label_source,
            label_threshold=settings.label_threshold,
            add_missing_indicators=settings.add_missing_indicators,
            apply_global_fill=True,
            settings=settings,
        )
        if settings.feature_lag_periods > 0:
            export_frame = apply_feature_lag(
                export_frame,
                feature_columns=get_feature_columns(
                    export_frame,
                    extra_drop=_extra_feature_drop(settings),
                ),
                lag_periods=int(settings.feature_lag_periods),
            )
        save_market_data(export_frame, settings.export_parquet)

    resolved_at_utc = datetime.now(timezone.utc).isoformat()
    git_commit = resolve_git_commit(ROOT)
    out_dir = Path(settings.output_dir)
    experiment_manifest = build_experiment_manifest(
        settings=settings,
        raw_frame=raw,
        model_frame=frame,
        model_id=model_adapter.model_id,
        model_target_column=model_adapter.training_target_column,
        output_dir=out_dir,
        git_commit=git_commit,
        resolved_at_utc=resolved_at_utc,
    )

    segment_a_spec = SegmentSpec(
        name="segment_a",
        train_start=settings.segment_a_train_start,
        train_end=settings.segment_a_train_end,
        valid_start=settings.segment_a_valid_start,
        valid_end=settings.segment_a_valid_end,
        rolling_start=settings.segment1_start,
        rolling_windows=settings.segment1_windows,
    )
    segment_b_spec = SegmentSpec(
        name="segment_b",
        train_start=settings.segment_b_train_start,
        train_end=settings.segment_b_train_end,
        valid_start=settings.segment_b_valid_start,
        valid_end=settings.segment_b_valid_end,
        rolling_start=settings.segment2_start,
        rolling_windows=settings.segment2_windows,
    )

    segment_a = fit_segment_model(
        frame=frame,
        spec=segment_a_spec,
        settings=settings,
        portfolio_cfg=portfolio_cfg,
        model_adapter=model_adapter,
        market_profile=market_profile,
        seed_offset=0,
    )
    segment_b = fit_segment_model(
        frame=frame,
        spec=segment_b_spec,
        settings=settings,
        portfolio_cfg=portfolio_cfg,
        model_adapter=model_adapter,
        market_profile=market_profile,
        seed_offset=1000,
    )

    bt_a = run_rolling_backtest(
        frame=frame,
        windows=build_rolling_windows(
            start_date=segment_a_spec.rolling_start,
            n_windows=segment_a_spec.rolling_windows,
            train_months=settings.train_months,
            gap_months=settings.gap_months,
            test_months=settings.test_months,
        ),
        feature_columns=segment_a.feature_columns,
        model_params=segment_a.model_params,
        model_adapter=model_adapter,
        target_column=model_adapter.training_target_column,
        random_state=settings.random_seed,
        cost_bps=settings.cost_bps,
        initial_nav=1.0,
        initial_signal_nav=1.0,
        add_missing_indicators=settings.add_missing_indicators,
        portfolio_config=portfolio_cfg,
        tradability_filter=lambda frame_slice: market_profile.filter_tradable_frame(
            frame_slice,
            settings=settings,
        ),
        missing_feature_policy=settings.missing_feature_policy,
    )
    bt_b = run_rolling_backtest(
        frame=frame,
        windows=build_rolling_windows(
            start_date=segment_b_spec.rolling_start,
            n_windows=segment_b_spec.rolling_windows,
            train_months=settings.train_months,
            gap_months=settings.gap_months,
            test_months=settings.test_months,
        ),
        feature_columns=segment_b.feature_columns,
        model_params=segment_b.model_params,
        model_adapter=model_adapter,
        target_column=model_adapter.training_target_column,
        random_state=settings.random_seed + 2000,
        cost_bps=settings.cost_bps,
        initial_nav=float(bt_a.nav.iloc[-1]) if not bt_a.nav.empty else 1.0,
        initial_signal_nav=float(bt_a.signal_nav.iloc[-1]) if not bt_a.signal_nav.empty else 1.0,
        add_missing_indicators=settings.add_missing_indicators,
        portfolio_config=portfolio_cfg,
        tradability_filter=lambda frame_slice: market_profile.filter_tradable_frame(
            frame_slice,
            settings=settings,
        ),
        missing_feature_policy=settings.missing_feature_policy,
    )

    strategy_nav = combine_backtest_segments(bt_a.nav, bt_b.nav, name="strategy_nav")
    signal_nav = combine_backtest_segments(bt_a.signal_nav, bt_b.signal_nav, name="signal_nav")
    strategy_returns = combine_backtest_segments(bt_a.period_returns, bt_b.period_returns, name="strategy_ret")
    signal_profit = combine_backtest_segments(
        bt_a.signal_period_profit,
        bt_b.signal_period_profit,
        name="signal_profit",
    )
    strategy_turnover = combine_backtest_segments(
        bt_a.period_turnover,
        bt_b.period_turnover,
        name="strategy_turnover",
    )
    signal_turnover = combine_backtest_segments(
        bt_a.signal_turnover,
        bt_b.signal_turnover,
        name="signal_turnover",
    )
    active_names = combine_backtest_segments(bt_a.active_names, bt_b.active_names, name="active_names")
    signal_active_names = combine_backtest_segments(
        bt_a.signal_active_names,
        bt_b.signal_active_names,
        name="signal_active_names",
    )
    period_ic = combine_backtest_segments(bt_a.period_ic, bt_b.period_ic, name="period_ic")
    period_rank_ic = combine_backtest_segments(bt_a.period_rank_ic, bt_b.period_rank_ic, name="period_rank_ic")
    portfolio_diagnostics = pd.concat([bt_a.portfolio_diagnostics, bt_b.portfolio_diagnostics])
    if not portfolio_diagnostics.empty:
        portfolio_diagnostics = portfolio_diagnostics.sort_index()
        portfolio_diagnostics = portfolio_diagnostics[
            ~portfolio_diagnostics.index.duplicated(keep="last")
        ]
    benchmark_nav = build_benchmark_nav(
        frame,
        strategy_nav.index,
        benchmark_cum_col="benchmark_cum_ret",
        benchmark_cum_mode=settings.benchmark_cum_mode,
    )
    benchmark_returns = benchmark_nav.pct_change().dropna()
    metrics = compute_performance_metrics(
        strategy_nav=strategy_nav,
        benchmark_nav=benchmark_nav,
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        strategy_turnover=strategy_turnover,
        active_names=active_names,
        period_ic=period_ic,
        period_rank_ic=period_rank_ic,
        periods_per_year=_periods_per_year_from_test_months(settings.test_months),
    )
    holdout_result: HoldoutResult | None = None
    if settings.holdout_start and settings.holdout_end:
        holdout_segment_fit = segment_a if settings.holdout_model_segment == "segment_a" else segment_b
        holdout_result = _build_holdout_result(
            frame=frame,
            holdout_start=settings.holdout_start,
            holdout_end=settings.holdout_end,
            model_segment=settings.holdout_model_segment,
            segment_fit=holdout_segment_fit,
            settings=settings,
            portfolio_cfg=portfolio_cfg,
            model_adapter=model_adapter,
            market_profile=market_profile,
        )

    run_config = build_run_config(
        settings=settings,
        segment_a_spec=segment_a_spec,
        segment_b_spec=segment_b_spec,
        segment_a=segment_a,
        segment_b=segment_b,
        experiment_manifest=experiment_manifest,
        holdout_result=holdout_result,
        factor_load_info=factor_load_info,
        input_load_info=input_load_info,
    )
    run_summary_text = build_run_summary_text(
        benchmark_name=settings.benchmark_name,
        strategy_nav=strategy_nav,
        strategy_turnover=strategy_turnover,
        period_ic=period_ic,
        period_rank_ic=period_rank_ic,
        segment_a=segment_a,
        segment_b=segment_b,
        metrics=metrics,
        tuning_cv_folds=settings.tuning_cv_folds,
        holdout_result=holdout_result,
    )
    write_outputs(
        out_dir=out_dir,
        benchmark_name=settings.benchmark_name,
        strategy_nav=strategy_nav,
        signal_nav=signal_nav,
        benchmark_nav=benchmark_nav,
        strategy_returns=strategy_returns,
        signal_profit=signal_profit,
        benchmark_returns=benchmark_returns,
        strategy_turnover=strategy_turnover,
        signal_turnover=signal_turnover,
        active_names=active_names,
        signal_active_names=signal_active_names,
        period_ic=period_ic,
        period_rank_ic=period_rank_ic,
        portfolio_diagnostics=portfolio_diagnostics,
        segment_a=segment_a,
        segment_b=segment_b,
        metrics=metrics,
        run_config=run_config,
        experiment_manifest=experiment_manifest,
        run_summary_text=run_summary_text,
    )
    if holdout_result is not None:
        write_holdout_outputs(
            out_dir=out_dir,
            holdout=holdout_result,
        )

    return {
        "output_dir": out_dir,
        "metrics": metrics,
        "run_summary_text": run_summary_text,
        "segment_a": segment_a,
        "segment_b": segment_b,
        "holdout_result": holdout_result,
    }


def print_run_results(results: dict[str, Any]) -> None:
    out_dir = results["output_dir"]
    segment_a = results["segment_a"]
    segment_b = results["segment_b"]
    holdout_result = results["holdout_result"]
    print(f"Output directory: {out_dir}")
    print(f"Segment A feature count: {len(segment_a.feature_columns)}")
    print(f"Segment B feature count: {len(segment_b.feature_columns)}")
    if holdout_result is not None:
        print(f"Holdout output directory: {out_dir / 'holdout'}")
    print()
    print(results["run_summary_text"])
    print()
    metrics = results["metrics"]
    if metrics:
        print(json.dumps(metrics, indent=2))
    else:
        print("No metrics were computed; verify strategy/benchmark date overlap.")
