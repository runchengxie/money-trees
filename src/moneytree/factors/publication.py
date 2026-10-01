from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from moneytree.data import ensure_date_ticker_index
from moneytree.factors.evaluate import compute_factor_ic, summarize_factor_ic

PUBLIC_SNAPSHOT_SCHEMA_VERSION = "1.1"
PUBLIC_SNAPSHOT_KIND = "moneytree_factor_evidence_snapshot"
_FORBIDDEN_PUBLIC_KEYS = {
    "ticker",
    "tickers",
    "positions",
    "weights",
    "portfolio_weights",
    "raw_path",
    "input_path",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _date_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def _factor_family(name: str) -> str:
    lowered = name.lower()
    for family in ("alpha101", "alpha191", "alpha158", "alpha360"):
        if family in lowered:
            return family
    return "custom"


def _group_returns(
    panel: pd.DataFrame,
    factor: str,
    return_column: str,
    group_count: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for date, group in panel.groupby(level="date", sort=True):
        values = pd.to_numeric(group[factor], errors="coerce")
        returns = pd.to_numeric(group[return_column], errors="coerce")
        valid = pd.concat([values.rename("factor"), returns.rename("return")], axis=1)
        valid = valid.replace([np.inf, -np.inf], np.nan).dropna()
        if valid.empty:
            continue
        ranks = valid["factor"].rank(method="first")
        buckets = pd.qcut(ranks, q=min(group_count, len(valid)), labels=False)
        for bucket, bucket_values in valid.assign(bucket=buckets).groupby("bucket"):
            rows.append(
                {
                    "date": date,
                    "group": int(bucket) + 1,
                    "mean_return": float(bucket_values["return"].mean()),
                }
            )

    if not rows:
        return []
    frame = pd.DataFrame(rows)
    summary = frame.groupby("group", sort=True).agg(
        mean_return=("mean_return", "mean"),
        periods=("date", "nunique"),
    )
    return [
        {
            "group": int(group),
            "mean_return": float(row["mean_return"]),
            "periods": int(row["periods"]),
        }
        for group, row in summary.iterrows()
    ]


def _benchmark_series_from_panel(panel: pd.DataFrame, column: str | None) -> pd.Series | None:
    if column is None:
        return None
    if column not in panel.columns:
        raise KeyError(f"Missing benchmark return column: {column}")
    benchmark = pd.to_numeric(panel[column], errors="coerce")
    benchmark.index = pd.to_datetime(panel.index.get_level_values("date"))
    return benchmark


def _daily_group_returns_for_date(
    group: pd.DataFrame,
    date: pd.Timestamp,
    factors: Sequence[str],
    return_column: str,
    group_count: int,
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    returns = pd.to_numeric(group[return_column], errors="coerce")
    for factor in factors:
        values = pd.to_numeric(group[factor], errors="coerce")
        valid = pd.concat([values.rename("factor"), returns.rename("return")], axis=1)
        valid = valid.replace([np.inf, -np.inf], np.nan).dropna()
        rows: list[dict[str, Any]] = []
        if not valid.empty:
            ranks = valid["factor"].rank(method="first")
            buckets = pd.qcut(ranks, q=min(group_count, len(valid)), labels=False)
            for bucket, bucket_values in valid.assign(bucket=buckets).groupby("bucket"):
                rows.append(
                    {
                        "group": int(bucket) + 1,
                        "mean_return": float(bucket_values["return"].mean()),
                    }
                )
        result[factor] = rows
    return result


def build_temporal_slices(
    daily_metrics: Mapping[str, Sequence[Mapping[str, Any]]],
    daily_group_returns: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    benchmark_returns: pd.Series | None = None,
    regime_window: int = 252,
    benchmark_name: str | None = None,
) -> dict[str, Any]:
    """Aggregate date-level factor diagnostics into annual and market regimes."""
    factors = list(daily_metrics)
    accumulator = TemporalSliceAccumulator(
        factors,
        benchmark_returns=benchmark_returns,
        regime_window=regime_window,
        benchmark_name=benchmark_name,
    )
    events: dict[pd.Timestamp, dict[str, Any]] = {}
    for factor, observations in daily_metrics.items():
        for item in observations:
            date = pd.Timestamp(item["date"]).normalize()
            value = item.get("rank_ic")
            events.setdefault(date, {"rank_ic": {}, "groups": {}})["rank_ic"][factor] = (
                float(value) if value is not None and np.isfinite(value) else np.nan
            )
    for factor, observations in daily_group_returns.items():
        for item in observations:
            date = pd.Timestamp(item["date"]).normalize()
            events.setdefault(date, {"rank_ic": {}, "groups": {}})["groups"].setdefault(
                factor, []
            ).append(item)
    for date, values in sorted(events.items()):
        accumulator.update(date, values["rank_ic"], values["groups"])
    return accumulator.result()


class TemporalSliceAccumulator:
    """Stream daily metrics into compact annual and regime aggregates."""

    def __init__(
        self,
        factors: Sequence[str],
        *,
        benchmark_returns: pd.Series | None = None,
        regime_window: int = 252,
        benchmark_name: str | None = None,
    ) -> None:
        if regime_window < 1:
            raise ValueError("regime_window must be at least 1")
        self.factors = list(factors)
        self.regime_window = regime_window
        self.benchmark_name = benchmark_name
        self.regime_by_date: dict[pd.Timestamp, str] = {}
        if benchmark_returns is not None:
            benchmark = pd.to_numeric(benchmark_returns, errors="coerce").copy()
            benchmark.index = pd.to_datetime(benchmark.index, errors="coerce").normalize()
            benchmark = benchmark.loc[benchmark.index.notna()].sort_index()
            if benchmark.index.has_duplicates:
                distinct = benchmark.groupby(level=0).nunique(dropna=True)
                if (distinct > 1).any():
                    raise ValueError("Benchmark returns must agree within each date")
                benchmark = benchmark.groupby(level=0).first()
            if (benchmark.dropna() <= -1).any():
                raise ValueError("Benchmark returns must be greater than -1")
            benchmark = benchmark.dropna()
            values = benchmark.to_numpy(dtype=float)
            for index in range(regime_window, len(values)):
                trailing_return = float(np.prod(1.0 + values[index - regime_window : index]) - 1.0)
                self.regime_by_date[benchmark.index[index]] = (
                    "bull" if trailing_return > 0 else "bear"
                )
        self.aggregates: dict[str, dict[str, dict[str, Any]]] = {
            factor: {} for factor in self.factors
        }

    def add_factors(self, factors: Iterable[str]) -> None:
        for factor in factors:
            factor = str(factor)
            if factor not in self.aggregates:
                self.factors.append(factor)
                self.aggregates[factor] = {}

    def update(
        self,
        date: object,
        rank_ic_by_factor: Mapping[str, float],
        group_returns_by_factor: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> None:
        date = pd.Timestamp(date).normalize()
        labels = [str(date.year)]
        regime = self.regime_by_date.get(date)
        if regime is not None:
            labels.append(regime)
        for factor in self.factors:
            rank_ic = rank_ic_by_factor.get(factor, np.nan)
            rank_ic = float(rank_ic) if rank_ic is not None else np.nan
            for label in labels:
                state = self.aggregates[factor].setdefault(
                    label,
                    {"rank_sum": 0.0, "rank_count": 0, "positive_count": 0, "groups": {}},
                )
                if np.isfinite(rank_ic):
                    state["rank_sum"] += rank_ic
                    state["rank_count"] += 1
                    state["positive_count"] += int(rank_ic > 0)
                for row in group_returns_by_factor.get(factor, []):
                    group = int(row["group"])
                    value = float(row["mean_return"])
                    if not np.isfinite(value):
                        continue
                    group_state = state["groups"].setdefault(group, [0.0, 0])
                    group_state[0] += value
                    group_state[1] += 1

    def result(self) -> dict[str, Any]:
        def render(factor: str, labels: Sequence[str]) -> list[dict[str, Any]]:
            rows = []
            for label in labels:
                state = self.aggregates[factor].get(label)
                if state is None:
                    continue
                count = state["rank_count"]
                rows.append(
                    {
                        "label": label,
                        "valid_dates": count,
                        "rank_ic_mean": state["rank_sum"] / count if count else None,
                        "rank_ic_positive_rate": state["positive_count"] / count if count else None,
                        "group_returns": [
                            {
                                "group": group,
                                "mean_return": total / periods,
                                "periods": periods,
                            }
                            for group, (total, periods) in sorted(state["groups"].items())
                        ],
                    }
                )
            return rows

        annual = {
            factor: render(
                factor,
                sorted(
                    (label for label in self.aggregates[factor] if label.isdigit()),
                    key=int,
                ),
            )
            for factor in self.factors
        }
        regimes = {
            factor: render(
                factor,
                [label for label in ("bull", "bear") if label in self.aggregates[factor]],
            )
            for factor in self.factors
        }
        if not self.regime_by_date:
            reason = (
                "benchmark_returns_not_supplied"
                if self.benchmark_name is None
                else "benchmark_window_insufficient"
            )
            regime_status = {"status": "not_provided", "reason": reason}
        else:
            regime_status = {"status": "complete", "reason": None}
        return {
            "annual": annual,
            "regime": regimes,
            "regime_status": regime_status,
            "regime_metadata": {
                "benchmark_name": self.benchmark_name,
                "rule": "trailing_compounded_return_v1"
                if self.benchmark_name is not None
                else None,
                "window": self.regime_window,
            },
        }


def build_factor_evidence_snapshot(
    frame: pd.DataFrame,
    factor_columns: Iterable[str],
    *,
    return_column: str = "next_period_return",
    data_version: str = "unknown",
    config: dict[str, Any] | None = None,
    git_metadata: dict[str, Any] | None = None,
    benchmark_return_column: str | None = None,
    benchmark_name: str | None = None,
    regime_window: int = 252,
) -> dict[str, Any]:
    """Build an aggregate-only, JSON-safe public factor evidence snapshot."""
    required = {"date", "ticker", return_column}
    available = set(frame.columns)
    if isinstance(frame.index, pd.MultiIndex):
        available.update(name for name in frame.index.names if name is not None)
    missing = sorted(required - available)
    if missing:
        raise KeyError(f"Missing required panel columns: {missing}")

    factors = [str(factor) for factor in factor_columns]
    missing_factors = sorted(set(factors) - set(frame.columns))
    if missing_factors:
        raise KeyError(f"Missing factor columns: {missing_factors}")
    if not factors:
        raise ValueError("At least one factor column is required")

    panel = ensure_date_ticker_index(frame)
    ic_frame = compute_factor_ic(panel, factors, return_column=return_column)
    summaries = summarize_factor_ic(ic_frame).set_index("factor")
    group_count = int((config or {}).get("group_count", 5))
    if group_count < 2:
        raise ValueError("group_count must be at least 2")

    temporal_accumulator = TemporalSliceAccumulator(
        factors,
        benchmark_returns=_benchmark_series_from_panel(panel, benchmark_return_column),
        regime_window=regime_window,
        benchmark_name=benchmark_name or benchmark_return_column,
    )
    rank_ic_by_date = {
        pd.Timestamp(date): dict(zip(group["factor"], group["rank_ic"], strict=False))
        for date, group in ic_frame.groupby("date", sort=True)
    }
    for date, group in panel.groupby(level="date", sort=True):
        date = pd.Timestamp(date)
        temporal_accumulator.update(
            date,
            rank_ic_by_date.get(date, {}),
            _daily_group_returns_for_date(group, date, factors, return_column, group_count),
        )
    temporal = temporal_accumulator.result()

    factor_payload: list[dict[str, Any]] = []
    for factor in factors:
        group = ic_frame.loc[ic_frame["factor"] == factor]
        summary = summaries.loc[factor] if factor in summaries.index else None
        valid_observations = int(group["n_obs"].sum()) if not group.empty else 0
        total_observations = int(len(panel))
        factor_payload.append(
            {
                "name": factor,
                "family": _factor_family(factor),
                "coverage": {
                    "valid_observations": valid_observations,
                    "total_observations": total_observations,
                    "ratio": (
                        float(valid_observations / total_observations)
                        if total_observations
                        else None
                    ),
                },
                "ic": {
                    "mean": summary["ic_mean"] if summary is not None else None,
                    "ir": summary["ic_ir"] if summary is not None else None,
                    "positive_rate": (
                        summary["ic_positive_rate"] if summary is not None else None
                    ),
                },
                "rank_ic": {
                    "mean": summary["rank_ic_mean"] if summary is not None else None,
                    "ir": summary["rank_ic_ir"] if summary is not None else None,
                    "positive_rate": (
                        summary["rank_ic_positive_rate"] if summary is not None else None
                    ),
                },
                "group_returns": _group_returns(panel, factor, return_column, group_count),
                "annual_slices": temporal["annual"].get(factor, []),
                "regime_slices": temporal["regime"].get(factor, []),
                "uncertainty": {
                    "status": "not_provided",
                    "reason": "holding_period_days_not_supplied",
                },
            }
        )

    dates = pd.to_datetime(panel.index.get_level_values("date"), errors="coerce").dropna()
    tickers = panel.index.get_level_values("ticker").nunique()
    payload = {
        "kind": PUBLIC_SNAPSHOT_KIND,
        "schema_version": PUBLIC_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_version": data_version,
        "code_revision": (git_metadata or {}).get("revision"),
        "dataset": {
            "date_start": _date_text(dates.min()) if len(dates) else None,
            "date_end": _date_text(dates.max()) if len(dates) else None,
            "trading_days": int(dates.nunique()),
            "ticker_count": int(tickers),
            "observation_count": int(len(panel)),
            "return_column": return_column,
        },
        "config": {"group_count": group_count},
        "factors": factor_payload,
        "uncertainty": {
            "status": "not_provided",
            "reason": "holding_period_days_not_supplied",
        },
        "temporal_validation": {
            "status": "partial" if temporal["regime_status"]["status"] != "complete" else "complete",
            "annual_status": "complete",
            "market_regime": temporal["regime_status"],
            "regime_metadata": temporal["regime_metadata"],
        },
        "multiple_testing": {
            "status": "not_provided",
            "reason": "holding_period_days_not_supplied",
        },
        "public_limits": [
            "Aggregate evidence only; no ticker-level values or portfolio weights.",
            "Evidence is descriptive research output and is not a return guarantee.",
        ],
    }
    return _json_safe(payload)


def audit_public_snapshot(payload: dict[str, Any]) -> None:
    """Reject public payloads containing forbidden private or non-JSON values."""

    def visit(value: Any, path: str = "snapshot") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in _FORBIDDEN_PUBLIC_KEYS:
                    raise ValueError(f"Forbidden public field: {path}.{key}")
                visit(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
        elif isinstance(value, float):
            if not np.isfinite(value):
                raise ValueError(f"Non-finite public value: {path}")
        elif isinstance(value, str) and (
            value.startswith("/") or (len(value) > 2 and value[1:3] == ":\\")
        ):
            raise ValueError(f"Absolute path in public payload: {path}")

    visit(payload)
