from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from moneytree.config import BacktestSettings, load_backtest_settings
from moneytree.factor_store import write_factor_store
from moneytree.markets import get_market_profile
from moneytree.models import get_model_adapter
from moneytree.portfolio import PortfolioConfig
from moneytree.runner import (
    HoldoutResult,
    SegmentFitResult,
    _build_holdout_result,
    build_run_summary_text,
    combine_backtest_segments,
)

DEFAULT_CONFIGS = [
    "configs/market/cn.yaml",
    "configs/model/rf.yaml",
    "configs/backtest/default.yaml",
]


def _build_smoke_dataset(freq: str = "QE") -> pd.DataFrame:
    start = "2004-03-31" if freq == "QE" else "2004-01-31"
    dates = pd.date_range(start, "2015-12-31", freq=freq)
    tickers = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ", "000006.SZ"]
    rows: list[dict[str, object]] = []

    for dt in dates:
        month_sign = 1.0 if dt.month % 2 == 1 else -1.0
        quarter_sign = 1.0 if dt.quarter in {1, 3} else -1.0
        benchmark_ret = 0.01 if dt.quarter in {1, 3} else -0.005
        benchmark_cum = 100.0 + 0.8 * len(rows)
        for i, ticker in enumerate(tickers):
            ticker_sign = 1.0 if i % 2 == 0 else -1.0
            rel = 0.08 * ticker_sign + 0.01 * quarter_sign + 0.005 * month_sign
            rows.append(
                {
                    "date": dt,
                    "ticker": ticker,
                    "f_signal": rel,
                    "f_rank": float(i),
                    "next_period_return": benchmark_ret + rel,
                    "benchmark_next_period_return": benchmark_ret,
                    "benchmark_cum_ret": benchmark_cum,
                    "is_suspended": False,
                    "is_st": False,
                    "hit_up_limit": False,
                    "hit_down_limit": False,
                }
            )
    return pd.DataFrame(rows)


def _build_cn_smoke_dataset(freq: str = "QE") -> pd.DataFrame:
    start = "2004-03-31" if freq == "QE" else "2004-01-31"
    dates = pd.date_range(start, "2015-12-31", freq=freq)
    tickers = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ", "000006.SZ"]
    rows: list[dict[str, object]] = []

    for dt in dates:
        benchmark_ret = 0.01 if dt.quarter in {1, 3} else -0.005
        benchmark_cum = 100.0 + 0.6 * len(rows)
        for i, ticker in enumerate(tickers):
            rel = 0.06 if i % 2 == 0 else -0.04
            rows.append(
                {
                    "date": dt,
                    "ticker": ticker,
                    "f_signal": rel + 0.001 * i,
                    "f_rank": float(i),
                    "next_period_return": benchmark_ret + rel,
                    "benchmark_next_period_return": benchmark_ret,
                    "benchmark_cum_ret": benchmark_cum,
                    "is_suspended": ticker == "000002.SZ" and dt.quarter == 2,
                    "is_st": ticker == "000003.SZ" and dt.quarter == 3,
                    "hit_up_limit": ticker == "000004.SZ" and dt.quarter == 4,
                    "hit_down_limit": ticker == "000005.SZ" and dt.quarter == 1 and dt.year % 2 == 0,
                }
            )
    return pd.DataFrame(rows)


def _cli_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    return env


def _cli_cmd(
    *,
    data_path: Path,
    output_dir: Path,
    extra_args: list[str] | None = None,
    config_paths: list[str] | None = None,
) -> list[str]:
    cmd = [sys.executable, "-m", "moneytree.cli.backtest"]
    for config_path in config_paths or DEFAULT_CONFIGS:
        cmd.extend(["--config", config_path])
    cmd.extend(["--data", str(data_path), "--output-dir", str(output_dir)])
    if extra_args:
        cmd.extend(extra_args)
    return cmd


def test_moneytree_cli_smoke(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "smoke.parquet"
    out_dir = tmp_path / "artifacts"
    _build_smoke_dataset().to_parquet(data_path, index=False)

    subprocess.run(
        _cli_cmd(
            data_path=data_path,
            output_dir=out_dir,
            extra_args=[
                "--set",
                "model.feature_selection=importance",
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
                "--set",
                "backtest.cost_bps=10",
            ],
        ),
        cwd=root,
        env=_cli_env(root),
        check=True,
    )

    required = [
        "strategy_nav.csv",
        "signal_nav.csv",
        "benchmark_nav.csv",
        "strategy_returns.csv",
        "benchmark_returns.csv",
        "signal_profit.csv",
        "strategy_turnover.csv",
        "active_names.csv",
        "ic_series.csv",
        "oos_period_diagnostics.csv",
        "strategy_vs_benchmark.csv",
        "notebook_report_navs.csv",
        "notebook_rolling_beta.csv",
        "notebook_residual_returns.csv",
        "notebook_residual_distribution.csv",
        "metrics.json",
        "run_config.json",
        "experiment_manifest.json",
        "run_summary.txt",
        "segment_a_features.txt",
        "segment_b_features.txt",
    ]
    for rel_path in required:
        assert (out_dir / rel_path).exists(), rel_path

    holdout_required = [
        "holdout/strategy_nav.csv",
        "holdout/signal_nav.csv",
        "holdout/benchmark_nav.csv",
        "holdout/strategy_returns.csv",
        "holdout/benchmark_returns.csv",
        "holdout/signal_profit.csv",
        "holdout/strategy_turnover.csv",
        "holdout/active_names.csv",
        "holdout/ic_series.csv",
        "holdout/oos_period_diagnostics.csv",
        "holdout/strategy_vs_benchmark.csv",
        "holdout/notebook_report_navs.csv",
        "holdout/notebook_rolling_beta.csv",
        "holdout/notebook_residual_returns.csv",
        "holdout/notebook_residual_distribution.csv",
        "holdout/metrics.json",
        "holdout/holdout_config.json",
    ]
    for rel_path in holdout_required:
        assert (out_dir / rel_path).exists(), rel_path

    config = json.loads((out_dir / "run_config.json").read_text(encoding="utf-8"))
    assert "arguments" in config
    assert config["benchmark"]["name"] == "000300.SH"
    assert config["benchmark"]["cum_mode"] == "nav"
    assert "segment_specs" in config
    assert config["segment_fits"]["segment_a"]["model_id"] == "random_forest"
    assert config["segment_fits"]["segment_a"]["train_start"]
    assert config["segment_fits"]["segment_a"]["valid_start"]
    assert config["segment_fits"]["segment_a"]["selected_feature_count"] > 0
    assert "holdout" in config
    assert config["holdout"]["enabled"] is True
    assert config["output_schema_version"] == "1.0"
    assert config["reproducibility"]["experiment_manifest_path"] == "experiment_manifest.json"
    assert config["reproducibility"]["input_data_sha256"]
    assert config["reproducibility"]["raw_input_schema_hash"]
    assert config["reproducibility"]["model_frame_schema_hash"]
    assert config["reproducibility"]["resolved_config_hash"]
    manifest = json.loads((out_dir / "experiment_manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_schema_version"] == "1.0"
    assert manifest["dataset"]["dataset_version"] == config["reproducibility"]["dataset_version"]
    assert manifest["input_data"]["sha256"] == config["reproducibility"]["input_data_sha256"]
    assert manifest["schemas"]["raw_input"]["schema_hash"]
    assert manifest["schemas"]["model_frame"]["schema_hash"]
    assert manifest["config"]["files_hash"]
    assert manifest["config"]["resolved_config_hash"]
    assert manifest["runtime"]["python"]
    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    assert "strategy_annualized_return" in metrics
    assert "strategy_max_drawdown" in metrics
    assert "avg_turnover_per_period" in metrics
    if np.isfinite(metrics["tracking_error_annualized"]) and metrics["tracking_error_annualized"] != 0:
        expected_ir = (
            metrics["avg_excess_return_per_period"] * 4.0 / metrics["tracking_error_annualized"]
        )
        assert np.isclose(metrics["information_ratio"], expected_ir)
    diagnostics = pd.read_csv(out_dir / "oos_period_diagnostics.csv")
    assert {
        "target_gross",
        "realized_gross",
        "target_net",
        "realized_net",
        "unallocated_exposure",
        "qp_fallback",
    }.issubset(diagnostics.columns)
    holdout_config = json.loads((out_dir / "holdout/holdout_config.json").read_text(encoding="utf-8"))
    assert holdout_config["model_segment"] == "segment_b"
    assert holdout_config["model_segment_train_start"]
    assert holdout_config["model_segment_valid_start"]

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


def test_moneytree_cli_holdout_uses_test_month_buckets(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "smoke_monthly.parquet"
    out_dir = tmp_path / "artifacts_monthly"
    _build_smoke_dataset(freq="ME").to_parquet(data_path, index=False)

    subprocess.run(
        _cli_cmd(
            data_path=data_path,
            output_dir=out_dir,
            extra_args=[
                "--set",
                "model.feature_selection=none",
                "--set",
                "model.n_trials=1",
                "--set",
                "backtest.segment1_windows=0",
                "--set",
                "backtest.segment2_windows=0",
                "--set",
                "backtest.test_months=3",
                "--set",
                "backtest.holdout.start=2015-01-01",
                "--set",
                "backtest.holdout.end=2015-12-31",
                "--set",
                "backtest.holdout.model_segment=segment_b",
                "--set",
                "backtest.cost_bps=10",
            ],
        ),
        cwd=root,
        env=_cli_env(root),
        check=True,
    )

    config = json.loads((out_dir / "run_config.json").read_text(encoding="utf-8"))
    assert config["holdout"]["enabled"] is True
    assert config["holdout"]["n_periods"] == 4

    holdout_returns = pd.read_csv(out_dir / "holdout/strategy_returns.csv")
    assert len(holdout_returns) == 4


def test_moneytree_cli_cn_config_stack_emits_benchmark_neutral_outputs(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "cn_smoke.parquet"
    out_dir = tmp_path / "cn_artifacts"
    _build_cn_smoke_dataset().to_parquet(data_path, index=False)

    subprocess.run(
        _cli_cmd(
            data_path=data_path,
            output_dir=out_dir,
            config_paths=[
                "configs/market/cn.yaml",
                "configs/model/rf.yaml",
                "configs/backtest/smoke.yaml",
            ],
            extra_args=[
                "--set",
                "model.feature_selection=none",
                "--set",
                "model.n_trials=0",
            ],
        ),
        cwd=root,
        env=_cli_env(root),
        check=True,
    )

    required = [
        "strategy_nav.csv",
        "signal_nav.csv",
        "benchmark_nav.csv",
        "strategy_returns.csv",
        "benchmark_returns.csv",
        "signal_profit.csv",
        "strategy_turnover.csv",
        "active_names.csv",
        "ic_series.csv",
        "oos_period_diagnostics.csv",
        "strategy_vs_benchmark.csv",
        "notebook_report_navs.csv",
        "notebook_rolling_beta.csv",
        "notebook_residual_returns.csv",
        "notebook_residual_distribution.csv",
        "metrics.json",
        "run_config.json",
        "run_summary.txt",
        "holdout/benchmark_nav.csv",
        "holdout/benchmark_returns.csv",
        "holdout/signal_nav.csv",
        "holdout/signal_profit.csv",
        "holdout/strategy_vs_benchmark.csv",
        "holdout/notebook_report_navs.csv",
    ]
    for rel_path in required:
        assert (out_dir / rel_path).exists(), rel_path

    config = json.loads((out_dir / "run_config.json").read_text(encoding="utf-8"))
    assert config["benchmark"]["name"] == "000300.SH"

    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    assert "benchmark_total_return" in metrics

    run_summary = (out_dir / "run_summary.txt").read_text(encoding="utf-8")
    assert "Performance vs 000300.SH" in run_summary


def test_moneytree_cli_uses_default_template_config_stack(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "default_stack.parquet"
    out_dir = tmp_path / "default_stack_artifacts"
    _build_smoke_dataset().to_parquet(data_path, index=False)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "moneytree.cli.backtest",
            "--data",
            str(data_path),
            "--output-dir",
            str(out_dir),
            "--set",
            "model.feature_selection=none",
            "--set",
            "model.n_trials=0",
            "--set",
            "backtest.segment1_windows=1",
            "--set",
            "backtest.segment2_windows=1",
            "--set",
            "backtest.holdout.start=2015-01-01",
            "--set",
            "backtest.holdout.end=2015-12-31",
        ],
        cwd=root,
        env=_cli_env(root),
        check=True,
    )

    run_config = json.loads((out_dir / "run_config.json").read_text(encoding="utf-8"))
    assert run_config["arguments"]["config_paths"] == DEFAULT_CONFIGS
    assert (out_dir / "metrics.json").exists()


def test_notebook_compat_preset_resolves_expected_overrides() -> None:
    settings = load_backtest_settings(
        config_paths=[
            "configs/market/cn.yaml",
            "configs/model/rf.yaml",
            "configs/backtest/default.yaml",
            "configs/preset/legacy_notebook_compat.yaml",
        ],
        data_path="dummy.parquet",
    )

    assert settings.label_source == "pred_rel_return"
    assert np.isclose(settings.label_threshold, 0.05)
    assert settings.feature_lag_periods == 0
    assert settings.feature_selection == "notebook_compat"
    assert settings.n_trials == 200
    assert settings.tuning_cv_folds == 1
    assert np.isclose(settings.cost_bps, 0.0)


def test_transitional_notebook_compat_preset_remains_available() -> None:
    legacy = load_backtest_settings(
        config_paths=[
            "configs/market/cn.yaml",
            "configs/model/rf.yaml",
            "configs/backtest/default.yaml",
            "configs/preset/legacy_notebook_compat.yaml",
        ],
        data_path="dummy.parquet",
    )
    transitional = load_backtest_settings(
        config_paths=[
            "configs/market/cn.yaml",
            "configs/model/rf.yaml",
            "configs/backtest/default.yaml",
            "configs/preset/notebook_compat.yaml",
        ],
        data_path="dummy.parquet",
    )

    assert transitional.feature_selection == legacy.feature_selection
    assert transitional.n_trials == legacy.n_trials
    assert transitional.feature_lag_periods == legacy.feature_lag_periods


def test_default_model_configs_disable_tuning() -> None:
    rf_settings = load_backtest_settings(
        config_paths=[
            "configs/market/cn.yaml",
            "configs/model/rf.yaml",
            "configs/backtest/default.yaml",
        ],
        data_path="dummy.parquet",
    )
    xgb_settings = load_backtest_settings(
        config_paths=[
            "configs/market/cn.yaml",
            "configs/model/xgb.yaml",
            "configs/backtest/default.yaml",
        ],
        data_path="dummy.parquet",
    )

    assert rf_settings.n_trials == 0
    assert rf_settings.tuning_cv_folds == 1
    assert xgb_settings.n_trials == 0
    assert xgb_settings.tuning_cv_folds == 1
    get_model_adapter("xgboost").validate_configuration(
        feature_selection=xgb_settings.feature_selection,
        n_trials=xgb_settings.n_trials,
    )


def test_tuning_preset_enables_explicit_tuning() -> None:
    settings = load_backtest_settings(
        config_paths=[
            "configs/market/cn.yaml",
            "configs/model/rf.yaml",
            "configs/backtest/default.yaml",
            "configs/preset/tuning.yaml",
        ],
        data_path="dummy.parquet",
    )

    assert settings.n_trials == 25
    assert settings.tuning_cv_folds == 3


def test_template_smoke_preset_resolves_local_run_values() -> None:
    settings = load_backtest_settings(
        config_paths=[
            "configs/market/cn.yaml",
            "configs/model/rf.yaml",
            "configs/backtest/smoke.yaml",
            "configs/preset/template_smoke.yaml",
        ],
    )

    assert settings.data == "./data_small.parquet"
    assert settings.output_dir == "./artifacts/template-smoke"
    assert settings.market_profile == "cn"
    assert settings.benchmark_name == "000300.SH"
    assert settings.benchmark_cum_mode == "nav"
    assert settings.missing_feature_policy == "error"


def test_backtest_settings_resolves_factor_selection_from_config() -> None:
    settings = load_backtest_settings(
        config_paths=[
            "configs/market/cn.yaml",
            "configs/model/rf.yaml",
            "configs/backtest/default.yaml",
        ],
        data_path="dummy.parquet",
        overrides=[
            'features.include_factor_families=["alpha158"]',
            "features.exclude_factor_prefixes=alpha360_",
            'features.exclude_factor_columns=["alpha191_030"]',
        ],
    )

    assert settings.include_factor_prefixes == ("alpha158_",)
    assert settings.exclude_factor_prefixes == ("alpha360_",)
    assert settings.exclude_factor_columns == ("alpha191_030",)


def test_backtest_settings_resolves_memory_safe_load_controls() -> None:
    settings = load_backtest_settings(
        config_paths=[
            "configs/market/cn.yaml",
            "configs/model/rf.yaml",
            "configs/backtest/default.yaml",
        ],
        data_path="dummy.parquet",
        overrides=[
            "backtest.load_mode=date_range",
            "backtest.load_warmup_days=120",
            "backtest.memory_budget_gb=8",
            "backtest.memory_budget_fraction=0.5",
        ],
    )

    assert settings.load_mode == "date_range"
    assert settings.load_warmup_days == 120
    assert np.isclose(settings.memory_budget_gb, 8.0)
    assert np.isclose(settings.memory_budget_fraction, 0.5)


def test_legacy_notebook_preset_enables_missing_feature_warning_policy() -> None:
    settings = load_backtest_settings(
        config_paths=[
            "configs/market/cn.yaml",
            "configs/model/rf.yaml",
            "configs/backtest/default.yaml",
            "configs/preset/legacy_notebook_compat.yaml",
        ],
        data_path="dummy.parquet",
    )

    assert settings.missing_feature_policy == "warn_fill_zero"


def test_backtest_settings_resolves_segment_date_overrides() -> None:
    settings = load_backtest_settings(
        config_paths=[
            "configs/market/cn.yaml",
            "configs/model/ridge.yaml",
            "configs/backtest/smoke.yaml",
        ],
        data_path="dummy.parquet",
        overrides=[
            "backtest.segment_a.train_start=2016-01-01",
            "backtest.segment_a.train_end=2017-01-01",
            "backtest.segment_a.valid_start=2017-04-01",
            "backtest.segment_a.valid_end=2017-07-01",
            "backtest.segment_b.train_start=2017-01-01",
            "backtest.segment_b.train_end=2018-01-01",
            "backtest.segment_b.valid_start=2018-04-01",
            "backtest.segment_b.valid_end=2018-07-01",
        ],
    )

    assert settings.segment_a_train_start == "2016-01-01"
    assert settings.segment_a_train_end == "2017-01-01"
    assert settings.segment_a_valid_start == "2017-04-01"
    assert settings.segment_a_valid_end == "2017-07-01"
    assert settings.segment_b_train_start == "2017-01-01"
    assert settings.segment_b_train_end == "2018-01-01"
    assert settings.segment_b_valid_start == "2018-04-01"
    assert settings.segment_b_valid_end == "2018-07-01"


def test_moneytree_cli_factor_prefix_selection_excludes_unselected_factors(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "factor_selection.parquet"
    out_dir = tmp_path / "factor_selection_artifacts"
    frame = _build_smoke_dataset()
    frame["alpha158_signal"] = frame["f_signal"]
    frame["alpha158_drop_me"] = frame["f_rank"]
    frame["alpha360_noise"] = frame["f_rank"]
    frame.to_parquet(data_path, index=False)

    subprocess.run(
        _cli_cmd(
            data_path=data_path,
            output_dir=out_dir,
            extra_args=[
                "--set",
                "model.feature_selection=none",
                "--set",
                "model.n_trials=0",
                "--set",
                "backtest.segment1_windows=1",
                "--set",
                "backtest.segment2_windows=1",
                "--set",
                'features.include_factor_prefixes=["alpha158_"]',
                "--set",
                'features.exclude_factor_columns=["alpha158_drop_me"]',
            ],
        ),
        cwd=root,
        env=_cli_env(root),
        check=True,
    )

    segment_a_features = (out_dir / "segment_a_features.txt").read_text(encoding="utf-8")
    run_config = json.loads((out_dir / "run_config.json").read_text(encoding="utf-8"))

    assert "alpha158_signal" in segment_a_features
    assert "alpha158_drop_me" not in segment_a_features
    assert "alpha360_noise" not in segment_a_features
    assert run_config["factor_selection"]["include_factor_prefixes"] == ["alpha158_"]
    assert run_config["factor_selection"]["exclude_factor_columns"] == ["alpha158_drop_me"]
    assert run_config["factor_selection"]["column_pruned"] is True


def test_moneytree_cli_loads_factor_store_manifest_with_selected_families(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    store_dir = tmp_path / "factor_store"
    out_dir = tmp_path / "factor_store_artifacts"
    frame = _build_smoke_dataset()
    frame["alpha158_signal"] = frame["f_signal"]
    frame["alpha158_drop_me"] = frame["f_rank"]
    frame["alpha360_noise"] = frame["f_rank"]
    write_factor_store(frame, store_dir)

    subprocess.run(
        _cli_cmd(
            data_path=store_dir / "manifest.json",
            output_dir=out_dir,
            extra_args=[
                "--set",
                "model.feature_selection=none",
                "--set",
                "model.n_trials=0",
                "--set",
                "backtest.segment1_windows=1",
                "--set",
                "backtest.segment2_windows=1",
                "--set",
                'features.include_factor_families=["alpha158"]',
                "--set",
                'features.exclude_factor_columns=["alpha158_drop_me"]',
            ],
        ),
        cwd=root,
        env=_cli_env(root),
        check=True,
    )

    segment_a_features = (out_dir / "segment_a_features.txt").read_text(encoding="utf-8")
    run_config = json.loads((out_dir / "run_config.json").read_text(encoding="utf-8"))

    assert "alpha158_signal" in segment_a_features
    assert "alpha158_drop_me" not in segment_a_features
    assert "alpha360_noise" not in segment_a_features
    assert run_config["factor_selection"]["source"] == "factor_store"
    assert run_config["factor_selection"]["include_factor_prefixes"] == ["alpha158_"]
    assert run_config["factor_selection"]["exclude_factor_columns"] == ["alpha158_drop_me"]
    assert run_config["input_load"]["mode"] == "auto"
    assert run_config["input_load"]["date_start"]
    assert run_config["input_load"]["date_end"]
    assert run_config["input_load"]["preflight"]["selected_families"] == ["alpha158"]


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
        model_id="random_forest",
        train_start="2019-01-01",
        train_end="2020-01-01",
        valid_start="2020-04-01",
        valid_end="2020-07-01",
        validation_profit=0.01,
        validation_turnover=0.5,
        validation_active_names=5,
        tuning_best_value=0.02,
        tuning_enabled=False,
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
        benchmark_name="000300.SH",
        strategy_nav=pd.Series([1.1, 1.2], index=idx, name="strategy_nav"),
        benchmark_nav=pd.Series([1.0, 1.01], index=idx, name="benchmark_nav"),
        strategy_returns=pd.Series([0.1, 0.09], index=idx, name="strategy_ret"),
        benchmark_returns=pd.Series([0.0, 0.01], index=idx, name="benchmark_ret"),
        strategy_turnover=pd.Series([0.5, 0.6], index=idx, name="strategy_turnover"),
        active_names=pd.Series([10, 12], index=idx, name="active_names"),
        signal_nav=pd.Series([1.05, 1.16], index=idx, name="signal_nav"),
        signal_profit=pd.Series([0.05, 0.10], index=idx, name="signal_profit"),
        signal_turnover=pd.Series([0.4, 0.5], index=idx, name="signal_turnover"),
        signal_active_names=pd.Series([9, 11], index=idx, name="signal_active_names"),
        period_ic=pd.Series([0.1, 0.2], index=idx, name="period_ic"),
        period_rank_ic=pd.Series([0.05, 0.15], index=idx, name="period_rank_ic"),
        portfolio_diagnostics=pd.DataFrame(
            {
                "target_gross": [1.0, 1.0],
                "realized_gross": [0.8, 0.9],
                "target_net": [0.0, 0.0],
                "realized_net": [0.0, 0.0],
                "unallocated_exposure": [0.2, 0.1],
                "qp_fallback": [False, False],
            },
            index=idx,
        ),
        model_segment_train_start="2019-01-01",
        model_segment_train_end="2021-12-31",
        model_segment_valid_start="2021-01-01",
        model_segment_valid_end="2021-03-31",
        metrics={"strategy_total_return": 0.1, "benchmark_total_return": 0.01},
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
        benchmark_name="000300.SH",
        strategy_nav=strategy_nav,
        strategy_turnover=pd.Series([0.2, 0.3], index=idx, name="strategy_turnover"),
        period_ic=pd.Series([0.1, np.nan], index=idx, name="period_ic"),
        period_rank_ic=pd.Series([0.05, np.nan], index=idx, name="period_rank_ic"),
        segment_a=_segment_stub(),
        segment_b=_segment_stub(),
        metrics={"strategy_total_return": 0.1, "benchmark_total_return": 0.05},
        tuning_cv_folds=1,
        holdout_result=_holdout_stub(*holdout_span),
    )

    assert f"Holdout overlap note: {expected_note}" in run_summary


def test_moneytree_cli_rejects_unpaired_holdout_dates(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "ignored.parquet"
    data_path.write_text("", encoding="utf-8")

    result = subprocess.run(
        _cli_cmd(
            data_path=data_path,
            output_dir=tmp_path / "unused",
            extra_args=["--set", "backtest.holdout.start=2024-01-01"],
        ),
        cwd=root,
        env=_cli_env(root),
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Use --holdout-start and --holdout-end together." in result.stderr


def test_moneytree_cli_rejects_test_months_below_one(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "ignored.parquet"
    data_path.write_text("", encoding="utf-8")

    result = subprocess.run(
        _cli_cmd(
            data_path=data_path,
            output_dir=tmp_path / "unused",
            extra_args=["--set", "backtest.test_months=0"],
        ),
        cwd=root,
        env=_cli_env(root),
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "--test-months must be >= 1." in result.stderr


def test_moneytree_cli_rejects_negative_feature_lag(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "ignored.parquet"
    data_path.write_text("", encoding="utf-8")

    result = subprocess.run(
        _cli_cmd(
            data_path=data_path,
            output_dir=tmp_path / "unused",
            extra_args=["--set", "market.feature_lag_periods=-1"],
        ),
        cwd=root,
        env=_cli_env(root),
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "--feature-lag-periods must be >= 0." in result.stderr


def test_moneytree_cli_rejects_missing_factor_prefix(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    data_path = tmp_path / "missing_prefix.parquet"
    _build_smoke_dataset().to_parquet(data_path, index=False)

    result = subprocess.run(
        _cli_cmd(
            data_path=data_path,
            output_dir=tmp_path / "unused",
            extra_args=["--set", 'features.include_factor_prefixes=["alpha101_"]'],
        ),
        cwd=root,
        env=_cli_env(root),
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Requested factor prefixes are missing from input data: alpha101_" in result.stderr


def test_build_holdout_result_rejects_inverted_holdout_span() -> None:
    with pytest.raises(ValueError, match="--holdout-start must be <= --holdout-end."):
        _build_holdout_result(
            frame=pd.DataFrame(),
            holdout_start="2024-02-01",
            holdout_end="2024-01-01",
            model_segment="segment_b",
            segment_fit=_segment_stub(),
            settings=BacktestSettings(data="dummy.parquet"),
            portfolio_cfg=PortfolioConfig(),
            model_adapter=get_model_adapter("random_forest"),
            market_profile=get_market_profile("cn"),
        )
