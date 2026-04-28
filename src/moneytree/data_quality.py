from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable
import warnings

import pandas as pd

from moneytree.data import MarketDataSanityReport, build_market_data_sanity_report

DATA_QUALITY_MODES = ("warn", "error")
DATA_QUALITY_MODES_WITH_OFF = ("off", *DATA_QUALITY_MODES)

TUSHARE_PANEL_REQUIRED_COLUMNS = (
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "next_period_return",
    "benchmark_cum_ret",
    "benchmark_next_period_return",
    "hit_up_limit",
    "hit_down_limit",
    "is_suspended",
    "is_st",
)
TUSHARE_PANEL_NULL_CHECK_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "next_period_return",
    "benchmark_cum_ret",
    "benchmark_next_period_return",
)
LOCAL_FACTOR_COUNTS = {"alpha158": 158, "alpha360": 360}


@dataclass(frozen=True)
class DataQualityResult:
    report: MarketDataSanityReport
    extra_errors: tuple[str, ...] = ()

    @property
    def errors(self) -> tuple[str, ...]:
        return (*self.report.errors, *self.extra_errors)

    @property
    def warnings(self) -> tuple[str, ...]:
        return self.report.warnings

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_lines(self, *, prefix: str = "[data:quality]") -> list[str]:
        lines = self.report.to_lines(prefix=prefix)
        if self.extra_errors:
            lines.append(f"{prefix} errors {'; '.join(self.extra_errors)}")
        return lines

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self.report)
        payload["warnings"] = list(self.warnings)
        payload["errors"] = list(self.errors)
        payload["extra_errors"] = list(self.extra_errors)
        payload["ok"] = self.ok
        return payload


def validate_data_quality_mode(
    mode: str,
    *,
    allow_off: bool = False,
    label: str = "data quality mode",
) -> str:
    normalized = str(mode).strip().lower()
    choices = DATA_QUALITY_MODES_WITH_OFF if allow_off else DATA_QUALITY_MODES
    if normalized not in choices:
        rendered = ", ".join(choices)
        raise ValueError(f"Unsupported {label} '{mode}'. Expected one of: {rendered}.")
    return normalized


def expected_local_factor_count(families: Iterable[str]) -> int:
    total = 0
    for family in families:
        key = str(family).strip().lower().replace("-", "_")
        total += LOCAL_FACTOR_COUNTS.get(key, 0)
    return total


def build_tushare_panel_quality_result(
    panel: pd.DataFrame,
    *,
    trade_dates: list[str] | None = None,
    expected_start: str | None = None,
    expected_end: str | None = None,
    factor_families: Iterable[str] = (),
) -> DataQualityResult:
    report = build_market_data_sanity_report(
        panel,
        required_columns=TUSHARE_PANEL_REQUIRED_COLUMNS,
        null_check_columns=TUSHARE_PANEL_NULL_CHECK_COLUMNS,
        expected_start=expected_start,
        expected_end=expected_end,
        expected_date_count=len(trade_dates) if trade_dates is not None else None,
    )
    extra_errors: list[str] = []
    expected_factor_count = expected_local_factor_count(factor_families)
    if expected_factor_count:
        factor_count = sum(
            str(column).startswith(("alpha158_", "alpha360_")) for column in panel.columns
        )
        if factor_count != expected_factor_count:
            extra_errors.append(
                f"local factor columns {factor_count} != expected {expected_factor_count}"
            )
    return DataQualityResult(report=report, extra_errors=tuple(extra_errors))


def enforce_data_quality_result(
    result: DataQualityResult,
    *,
    mode: str,
    error_message: str,
    warning_message: str,
) -> None:
    normalized = validate_data_quality_mode(mode, allow_off=True)
    if normalized == "off" or result.ok:
        return
    message = "; ".join(result.errors)
    if normalized == "error":
        raise ValueError(f"{error_message}: {message}")
    warnings.warn(
        f"{warning_message}: {message}",
        RuntimeWarning,
        stacklevel=2,
    )
