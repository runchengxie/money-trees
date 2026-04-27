from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

from moneytree.data import normalize_factor_prefixes

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None  # type: ignore[assignment]


def _parse_scalar(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _set_nested(mapping: dict[str, Any], dotted_key: str, value: Any) -> None:
    current = mapping
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _deep_copy_dict(mapping: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(mapping))


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_copy_dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple, set)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    raise ValueError(f"Expected a string or list of strings, got {type(value).__name__}.")


def _load_mapping(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        return json.loads(file_path.read_text(encoding="utf-8"))
    if suffix == ".toml":
        if tomllib is None:
            raise RuntimeError("TOML config requires Python 3.11+ or the tomli package.")
        return tomllib.loads(file_path.read_text(encoding="utf-8"))
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "YAML config requires the optional PyYAML dependency."
            ) from exc
        loaded = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        return loaded or {}
    raise ValueError(f"Unsupported config format: {file_path}")


def _resolve_config_paths(
    *,
    config_paths: list[str | Path] | None = None,
    config_path: str | Path | None = None,
) -> list[Path]:
    resolved: list[Path] = []
    for raw_path in config_paths or []:
        resolved.append(Path(raw_path))
    if config_path is not None:
        resolved.append(Path(config_path))
    if not resolved:
        raise ValueError("At least one config path is required.")
    return resolved


@dataclass
class BacktestSettings:
    data: str
    output_dir: str = "artifacts/backtest"
    market_profile: str = "cn"
    benchmark_name: str = "000300.SH"
    benchmark_return_column: str = "benchmark_next_period_return"
    benchmark_cum_column: str = "benchmark_cum_ret"
    market_tradability_columns: dict[str, str] = field(default_factory=dict)
    market_tradability_filters: dict[str, bool] = field(default_factory=dict)
    model_id: str = "random_forest"
    model_params: dict[str, Any] = field(default_factory=dict)
    label_source: str = "actual"
    label_threshold: float = 0.03
    add_missing_indicators: bool = False
    cost_bps: float = 10.0
    portfolio_min_score: float = 0.05
    portfolio_winsor_z: float = 3.0
    portfolio_weighting_method: str = "heuristic"
    portfolio_gross_target: float = 1.0
    portfolio_net_target: float = 0.0
    portfolio_max_name_weight: float = 0.02
    portfolio_min_names_per_side: int = 5
    portfolio_vol_scaling: str = "on"
    portfolio_vol_power: float = 1.0
    portfolio_sector_neutral: str = "off"
    portfolio_sector_prefix: str = "SP_sector_code_"
    portfolio_qp_risk_aversion: float = 10.0
    portfolio_qp_turnover_penalty: float = 5.0
    portfolio_qp_cov_lookback: int = 252
    portfolio_qp_cov_shrinkage: str = "on"
    portfolio_qp_cov_ridge: float = 1e-6
    portfolio_qp_mu_clip: float = 1.0
    portfolio_qp_max_names: int = 300
    portfolio_qp_solver_max_iter: int = 300
    portfolio_qp_solver_ftol: float = 1e-9
    portfolio_qp_fallback_to_heuristic: str = "on"
    n_trials: int = 0
    tuning_cv_folds: int = 1
    feature_selection: str = "importance"
    min_features: int = 2
    max_selection_steps: int = 200
    random_seed: int = 123
    include_factor_prefixes: tuple[str, ...] = ()
    exclude_factor_prefixes: tuple[str, ...] = ()
    feature_lag_periods: int = 1
    train_months: int = 60
    gap_months: int = 3
    test_months: int = 3
    segment1_start: str = "2004-04-01"
    segment1_windows: int = 60
    segment2_start: str = "2009-04-01"
    segment2_windows: int = 20
    holdout_start: str = ""
    holdout_end: str = ""
    holdout_model_segment: str = "segment_b"
    export_parquet: str = ""
    config_path: str = ""
    config_paths: list[str] = field(default_factory=list)
    resolved_config: dict[str, Any] = field(default_factory=dict)

    def to_display_config(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["resolved_config"] = _deep_copy_dict(self.resolved_config)
        return payload


def load_backtest_settings(
    *,
    config_paths: list[str | Path] | None = None,
    config_path: str | Path | None = None,
    data_path: str | None = None,
    output_dir: str | None = None,
    overrides: list[str] | None = None,
) -> BacktestSettings:
    resolved_paths = _resolve_config_paths(config_paths=config_paths, config_path=config_path)
    mapping: dict[str, Any] = {}
    for path in resolved_paths:
        mapping = _deep_merge_dict(mapping, _load_mapping(path))
    for override in overrides or []:
        if "=" not in override:
            raise ValueError(f"Invalid override '{override}'. Use dotted.path=value.")
        key, value = override.split("=", 1)
        _set_nested(mapping, key.strip(), _parse_scalar(value.strip()))

    market = mapping.get("market", {})
    features = mapping.get("features", {})
    model = mapping.get("model", {})
    portfolio = mapping.get("portfolio", {})
    backtest = mapping.get("backtest", {})
    holdout = backtest.get("holdout", {})
    output = mapping.get("output", {})

    resolved_data = data_path or market.get("data_path") or output.get("data_path")
    if not resolved_data:
        raise ValueError("A data path is required via config or --data.")
    resolved_output_dir = output_dir or output.get("output_dir", "artifacts/backtest")

    settings = BacktestSettings(
        data=str(resolved_data),
        output_dir=str(resolved_output_dir),
        market_profile=str(market.get("profile", "cn")),
        benchmark_name=str(market.get("benchmark", "000300.SH")),
        benchmark_return_column=str(
            market.get(
                "benchmark_return_column",
                "benchmark_next_period_return",
            )
        ),
        benchmark_cum_column=str(
            market.get(
                "benchmark_cum_column",
                "benchmark_cum_ret",
            )
        ),
        market_tradability_columns=dict(market.get("tradability_columns", {})),
        market_tradability_filters={
            "suspend": bool(market.get("tradability_filters", {}).get("suspend", False)),
            "st": bool(market.get("tradability_filters", {}).get("st", False)),
            "up_limit": bool(market.get("tradability_filters", {}).get("up_limit", False)),
            "down_limit": bool(market.get("tradability_filters", {}).get("down_limit", False)),
        },
        model_id=str(model.get("id", "random_forest")),
        model_params=dict(model.get("params", {})),
        label_source=str(market.get("label_source", "actual")),
        label_threshold=float(market.get("label_threshold", 0.03)),
        add_missing_indicators=bool(market.get("add_missing_indicators", False)),
        cost_bps=float(backtest.get("cost_bps", 10.0)),
        portfolio_min_score=float(portfolio.get("min_score", 0.05)),
        portfolio_winsor_z=float(portfolio.get("winsor_z", 3.0)),
        portfolio_weighting_method=str(portfolio.get("weighting_method", "heuristic")),
        portfolio_gross_target=float(portfolio.get("gross_target", 1.0)),
        portfolio_net_target=float(portfolio.get("net_target", 0.0)),
        portfolio_max_name_weight=float(portfolio.get("max_name_weight", 0.02)),
        portfolio_min_names_per_side=int(portfolio.get("min_names_per_side", 5)),
        portfolio_vol_scaling="on" if bool(portfolio.get("use_vol_scaling", True)) else "off",
        portfolio_vol_power=float(portfolio.get("vol_power", 1.0)),
        portfolio_sector_neutral="on" if bool(portfolio.get("sector_neutral", False)) else "off",
        portfolio_sector_prefix=str(portfolio.get("sector_prefix", "SP_sector_code_")),
        portfolio_qp_risk_aversion=float(portfolio.get("qp_risk_aversion", 10.0)),
        portfolio_qp_turnover_penalty=float(portfolio.get("qp_turnover_penalty", 5.0)),
        portfolio_qp_cov_lookback=int(portfolio.get("qp_cov_lookback", 252)),
        portfolio_qp_cov_shrinkage="on"
        if bool(portfolio.get("qp_cov_shrinkage", True))
        else "off",
        portfolio_qp_cov_ridge=float(portfolio.get("qp_cov_ridge", 1e-6)),
        portfolio_qp_mu_clip=float(portfolio.get("qp_mu_clip", 1.0)),
        portfolio_qp_max_names=int(portfolio.get("qp_max_names", 300)),
        portfolio_qp_solver_max_iter=int(portfolio.get("qp_solver_max_iter", 300)),
        portfolio_qp_solver_ftol=float(portfolio.get("qp_solver_ftol", 1e-9)),
        portfolio_qp_fallback_to_heuristic="on"
        if bool(portfolio.get("qp_fallback_to_heuristic", True))
        else "off",
        n_trials=int(model.get("n_trials", 0)),
        tuning_cv_folds=int(model.get("tuning_cv_folds", 1)),
        feature_selection=str(model.get("feature_selection", "importance")),
        min_features=int(model.get("min_features", 2)),
        max_selection_steps=int(model.get("max_selection_steps", 200)),
        random_seed=int(model.get("random_seed", 123)),
        include_factor_prefixes=normalize_factor_prefixes(
            _as_str_tuple(features.get("include_factor_prefixes")),
            families=_as_str_tuple(features.get("include_factor_families")),
        ),
        exclude_factor_prefixes=normalize_factor_prefixes(
            _as_str_tuple(features.get("exclude_factor_prefixes")),
            families=_as_str_tuple(features.get("exclude_factor_families")),
        ),
        feature_lag_periods=int(market.get("feature_lag_periods", 1)),
        train_months=int(backtest.get("train_months", 60)),
        gap_months=int(backtest.get("gap_months", 3)),
        test_months=int(backtest.get("test_months", 3)),
        segment1_start=str(backtest.get("segment1_start", "2004-04-01")),
        segment1_windows=int(backtest.get("segment1_windows", 60)),
        segment2_start=str(backtest.get("segment2_start", "2009-04-01")),
        segment2_windows=int(backtest.get("segment2_windows", 20)),
        holdout_start=str(holdout.get("start", "")),
        holdout_end=str(holdout.get("end", "")),
        holdout_model_segment=str(holdout.get("model_segment", "segment_b")),
        export_parquet=str(output.get("export_parquet", "")),
        config_path=str(resolved_paths[-1]),
        config_paths=[str(path) for path in resolved_paths],
        resolved_config=_deep_copy_dict(mapping),
    )
    return settings
