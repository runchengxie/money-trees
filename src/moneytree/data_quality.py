from __future__ import annotations

import warnings
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
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
TUSHARE_PANEL_PRICE_COLUMNS = ("open", "high", "low", "close", "vwap")
ADJUSTED_PRICE_COLUMN_PAIRS = {
    "open_adj": "open",
    "high_adj": "high",
    "low_adj": "low",
    "close_adj": "close",
    "vwap_adj": "vwap",
}
ADJUSTED_PRICE_NULL_CHECK_COLUMNS = ("adj_factor", *ADJUSTED_PRICE_COLUMN_PAIRS)
RETURN_CONSISTENCY_ATOL = 1e-10
RETURN_CONSISTENCY_RTOL = 1e-7
ADJUSTED_PRICE_ATOL = 1e-8
ADJUSTED_PRICE_RTOL = 1e-7
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


def _date_text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).date().isoformat()


def _null_rates(null_counts: dict[str, int], rows: int) -> dict[str, float]:
    if rows <= 0:
        return {column: 0.0 for column in null_counts}
    return {column: float(count) / float(rows) for column, count in null_counts.items()}


def _count_series_mismatches(
    actual: pd.Series,
    expected: pd.Series,
    *,
    rtol: float = RETURN_CONSISTENCY_RTOL,
    atol: float = RETURN_CONSISTENCY_ATOL,
) -> dict[str, int]:
    actual_values = pd.to_numeric(actual, errors="coerce")
    expected_values = pd.to_numeric(expected, errors="coerce")
    actual_null = actual_values.isna()
    expected_null = expected_values.isna()
    comparable = ~(actual_null | expected_null)
    if comparable.any():
        close = np.isclose(
            actual_values[comparable].to_numpy(dtype="float64", copy=False),
            expected_values[comparable].to_numpy(dtype="float64", copy=False),
            rtol=rtol,
            atol=atol,
            equal_nan=True,
        )
        mismatch_count = int((~close).sum())
    else:
        mismatch_count = 0
    return {
        "mismatch_count": mismatch_count,
        "unexpected_null_count": int((actual_null & ~expected_null).sum()),
        "unexpected_non_null_count": int((~actual_null & expected_null).sum()),
    }


def _quality_status(errors: list[str]) -> str:
    return "ok" if not errors else "error"


def _derive_return_consistency(frame: pd.DataFrame, schema_names: set[str]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    result: dict[str, Any] = {
        "checked": False,
        "errors": errors,
        "warnings": warnings,
    }

    price_source = "close_adj" if "close_adj" in schema_names else "close"
    ticker_return_columns = {"date", "ticker", price_source, "return_1d", "next_period_return"}
    if ticker_return_columns.issubset(frame.columns):
        result["checked"] = True
        ordered = frame.loc[:, ["date", "ticker", price_source]].copy()
        ordered["_row"] = np.arange(len(ordered), dtype="int64")
        ordered["_date"] = pd.to_datetime(ordered["date"], errors="coerce")
        ordered["_ticker"] = ordered["ticker"].astype(str)
        ordered = ordered.sort_values(["_ticker", "_date", "_row"], kind="mergesort")
        prices = pd.to_numeric(ordered[price_source], errors="coerce")
        grouped = prices.groupby(ordered["_ticker"], sort=False)
        expected_return = grouped.pct_change()
        expected_next = expected_return.groupby(ordered["_ticker"], sort=False).shift(-1)
        return_expected = pd.Series(index=ordered["_row"], data=expected_return.to_numpy()).sort_index()
        next_expected = pd.Series(index=ordered["_row"], data=expected_next.to_numpy()).sort_index()
        return_check = _count_series_mismatches(frame["return_1d"], return_expected)
        next_check = _count_series_mismatches(frame["next_period_return"], next_expected)
        result.update(
            {
                "price_source": price_source,
                "return_1d": return_check,
                "next_period_return": next_check,
            }
        )
        for column, check in (("return_1d", return_check), ("next_period_return", next_check)):
            if any(check.values()):
                errors.append(
                    f"{column} consistency failed: mismatches={check['mismatch_count']} "
                    f"unexpected_nulls={check['unexpected_null_count']} "
                    f"unexpected_non_nulls={check['unexpected_non_null_count']}"
                )
    else:
        missing = sorted(ticker_return_columns.difference(frame.columns))
        result["ticker_return_skipped_missing_columns"] = missing

    benchmark_columns = {
        "date",
        "benchmark_close",
        "benchmark_return",
        "benchmark_next_period_return",
    }
    if benchmark_columns.issubset(frame.columns):
        result["checked"] = True
        benchmark = (
            frame.loc[:, ["date", "benchmark_close"]]
            .drop_duplicates(subset=["date"], keep="last")
            .copy()
        )
        benchmark["_date"] = pd.to_datetime(benchmark["date"], errors="coerce")
        benchmark = benchmark.sort_values("_date", kind="mergesort")
        benchmark_close = pd.to_numeric(benchmark["benchmark_close"], errors="coerce")
        expected_benchmark_return = benchmark_close.pct_change()
        expected_benchmark_next = expected_benchmark_return.shift(-1)
        return_map = pd.Series(expected_benchmark_return.to_numpy(), index=benchmark["date"])
        next_map = pd.Series(expected_benchmark_next.to_numpy(), index=benchmark["date"])
        benchmark_return_expected = frame["date"].map(return_map)
        benchmark_next_expected = frame["date"].map(next_map)
        benchmark_return_check = _count_series_mismatches(
            frame["benchmark_return"],
            benchmark_return_expected,
        )
        benchmark_next_check = _count_series_mismatches(
            frame["benchmark_next_period_return"],
            benchmark_next_expected,
        )
        result.update(
            {
                "benchmark_return": benchmark_return_check,
                "benchmark_next_period_return": benchmark_next_check,
            }
        )
        for column, check in (
            ("benchmark_return", benchmark_return_check),
            ("benchmark_next_period_return", benchmark_next_check),
        ):
            if any(check.values()):
                errors.append(
                    f"{column} consistency failed: mismatches={check['mismatch_count']} "
                    f"unexpected_nulls={check['unexpected_null_count']} "
                    f"unexpected_non_nulls={check['unexpected_non_null_count']}"
                )
    else:
        missing = sorted(benchmark_columns.difference(frame.columns))
        result["benchmark_return_skipped_missing_columns"] = missing
    result["status"] = _quality_status(errors)
    return result


def _derive_adjusted_price_consistency(frame: pd.DataFrame, schema_names: set[str]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    result: dict[str, Any] = {
        "checked": False,
        "errors": errors,
        "warnings": warnings,
        "null_counts": {},
        "mismatch_counts": {},
    }
    available_adjusted = [
        adjusted
        for adjusted, raw in ADJUSTED_PRICE_COLUMN_PAIRS.items()
        if adjusted in schema_names and raw in schema_names
    ]
    if "adj_factor" not in schema_names or not available_adjusted:
        result["skipped_missing_columns"] = sorted(
            {"adj_factor"}.union(ADJUSTED_PRICE_COLUMN_PAIRS).difference(schema_names)
        )
        result["status"] = "ok"
        return result

    result["checked"] = True
    for column in ("adj_factor", *available_adjusted):
        count = int(frame[column].isna().sum())
        result["null_counts"][column] = count
        if count:
            errors.append(f"{column} has {count} null adjusted-price values")

    factor = pd.to_numeric(frame["adj_factor"], errors="coerce")
    for adjusted in available_adjusted:
        raw = ADJUSTED_PRICE_COLUMN_PAIRS[adjusted]
        raw_values = pd.to_numeric(frame[raw], errors="coerce")
        adjusted_values = pd.to_numeric(frame[adjusted], errors="coerce")
        expected = raw_values * factor
        comparable = ~(raw_values.isna() | factor.isna() | adjusted_values.isna())
        if comparable.any():
            close = np.isclose(
                adjusted_values[comparable].to_numpy(dtype="float64", copy=False),
                expected[comparable].to_numpy(dtype="float64", copy=False),
                rtol=ADJUSTED_PRICE_RTOL,
                atol=ADJUSTED_PRICE_ATOL,
                equal_nan=True,
            )
            mismatch_count = int((~close).sum())
        else:
            mismatch_count = 0
        result["mismatch_counts"][adjusted] = mismatch_count
        if mismatch_count:
            errors.append(f"{adjusted} != {raw} * adj_factor in {mismatch_count} rows")

    result["status"] = _quality_status(errors)
    return result


def _parquet_narrow_frame(path: Path, columns: list[str]) -> pd.DataFrame:
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - pyarrow is a core dependency
        raise RuntimeError("Parquet quality inspection requires the pyarrow dependency.") from exc

    table = pq.read_table(path, columns=columns)
    return table.to_pandas(ignore_metadata=True, split_blocks=True, self_destruct=True)


def _exact_parquet_duplicate_key_count(path: Path) -> int:
    keys = _parquet_narrow_frame(path, ["date", "ticker"])
    if not {"date", "ticker"}.issubset(keys.columns):
        return 0
    return int(keys.duplicated(subset=["date", "ticker"]).sum())


def build_parquet_panel_quality_payload(
    path: str | Path,
    *,
    batch_size: int = 250_000,
    max_null_rate: float = 0.05,
) -> dict[str, Any]:
    """Inspect a Money Trees parquet panel without loading every column at once."""
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - pyarrow is a core dependency
        raise RuntimeError("Parquet quality inspection requires the pyarrow dependency.") from exc

    file_path = Path(path)
    parquet_file = pq.ParquetFile(file_path)
    schema_names = set(parquet_file.schema_arrow.names)
    required = tuple(TUSHARE_PANEL_REQUIRED_COLUMNS)
    null_columns = tuple(
        column
        for column in dict.fromkeys(
            (*TUSHARE_PANEL_NULL_CHECK_COLUMNS, *ADJUSTED_PRICE_NULL_CHECK_COLUMNS)
        )
        if column in schema_names
    )
    price_columns = tuple(
        column
        for column in dict.fromkeys(
            (*TUSHARE_PANEL_PRICE_COLUMNS, *ADJUSTED_PRICE_COLUMN_PAIRS)
        )
        if column in schema_names
    )
    scan_columns = [
        column
        for column in dict.fromkeys(("date", "ticker", *null_columns, *price_columns, "volume", "high", "low"))
        if column in schema_names
    ]

    rows = 0
    date_values: set[str] = set()
    ticker_values: set[str] = set()
    date_min: pd.Timestamp | None = None
    date_max: pd.Timestamp | None = None
    null_counts = {column: 0 for column in null_columns}
    non_positive_price_counts = {column: 0 for column in price_columns}
    negative_volume_count = 0
    inverted_ohlc_count = 0
    invalid_date_count = 0
    missing_ticker_count = 0
    adjacent_duplicate_count = 0
    out_of_order_count = 0
    previous_key: tuple[pd.Timestamp, str] | None = None

    if scan_columns:
        for batch in parquet_file.iter_batches(batch_size=batch_size, columns=scan_columns):
            frame = batch.to_pandas(ignore_metadata=True)
            batch_rows = int(len(frame))
            rows += batch_rows

            if "date" in frame.columns:
                parsed_dates = pd.to_datetime(frame["date"], errors="coerce")
                valid_dates = parsed_dates.dropna()
                invalid_date_count += int(parsed_dates.isna().sum())
                if not valid_dates.empty:
                    current_min = pd.Timestamp(valid_dates.min())
                    current_max = pd.Timestamp(valid_dates.max())
                    date_min = current_min if date_min is None else min(date_min, current_min)
                    date_max = current_max if date_max is None else max(date_max, current_max)
                    date_values.update(
                        pd.Timestamp(value).date().isoformat() for value in valid_dates.unique()
                    )
            else:
                parsed_dates = pd.Series(pd.NaT, index=frame.index)
                invalid_date_count += batch_rows

            if "ticker" in frame.columns:
                tickers = frame["ticker"]
                missing_ticker_count += int(tickers.isna().sum())
                ticker_values.update(str(value) for value in tickers.dropna().unique())
            else:
                tickers = pd.Series(np.nan, index=frame.index)
                missing_ticker_count += batch_rows

            if {"date", "ticker"}.issubset(frame.columns):
                key_frame = pd.DataFrame(
                    {
                        "date": parsed_dates,
                        "ticker": tickers.astype(str),
                    }
                )
                previous_dates = key_frame["date"].shift(1)
                previous_tickers = key_frame["ticker"].shift(1)
                if previous_key is not None and batch_rows:
                    previous_dates.iloc[0] = previous_key[0]
                    previous_tickers.iloc[0] = previous_key[1]
                valid_previous = previous_dates.notna()
                adjacent_duplicate_count += int(
                    (
                        valid_previous
                        & (key_frame["date"] == previous_dates)
                        & (key_frame["ticker"] == previous_tickers)
                    ).sum()
                )
                out_of_order_count += int(
                    (
                        valid_previous
                        & (
                            (key_frame["date"] < previous_dates)
                            | (
                                (key_frame["date"] == previous_dates)
                                & (key_frame["ticker"] < previous_tickers)
                            )
                        )
                    ).sum()
                )
                if batch_rows:
                    previous_key = (key_frame["date"].iloc[-1], key_frame["ticker"].iloc[-1])

            for column in null_counts:
                null_counts[column] += int(frame[column].isna().sum())
            for column in non_positive_price_counts:
                values = pd.to_numeric(frame[column], errors="coerce")
                non_positive_price_counts[column] += int((values <= 0).sum())
            if "volume" in frame.columns:
                volume = pd.to_numeric(frame["volume"], errors="coerce")
                negative_volume_count += int((volume < 0).sum())
            if {"high", "low"}.issubset(frame.columns):
                high = pd.to_numeric(frame["high"], errors="coerce")
                low = pd.to_numeric(frame["low"], errors="coerce")
                inverted_ohlc_count += int((high < low).sum())
    else:
        rows = int(parquet_file.metadata.num_rows)

    missing_required = tuple(sorted(column for column in required if column not in schema_names))
    null_rates = _null_rates(null_counts, rows)
    warnings_list: list[str] = []
    errors: list[str] = []
    if missing_required:
        errors.append(f"missing required columns: {list(missing_required)}")
    if rows == 0:
        errors.append("frame is empty")
    if "date" not in schema_names or "ticker" not in schema_names:
        errors.append("missing date/ticker key fields")
    if invalid_date_count:
        errors.append(f"date keys invalid or missing: {invalid_date_count}")
    if missing_ticker_count:
        errors.append(f"ticker keys missing: {missing_ticker_count}")
    duplicate_check_exact = bool(out_of_order_count == 0)
    if out_of_order_count and {"date", "ticker"}.issubset(schema_names):
        adjacent_duplicate_count = _exact_parquet_duplicate_key_count(file_path)
        duplicate_check_exact = True
    if adjacent_duplicate_count:
        errors.append(f"duplicate date/ticker keys: {adjacent_duplicate_count}")
    if out_of_order_count:
        warnings_list.append(
            f"date/ticker keys out of sorted order in {out_of_order_count} rows; "
            "duplicate_key_count computed with an exact narrow-column fallback"
        )
    for column, rate in null_rates.items():
        if rate > float(max_null_rate):
            warnings_list.append(f"{column} null_rate {rate:.4f} > {float(max_null_rate):.4f}")
    for column, count in non_positive_price_counts.items():
        if count:
            warnings_list.append(f"{column} has {count} non-positive values")
    if negative_volume_count:
        warnings_list.append(f"volume has {negative_volume_count} negative values")
    if inverted_ohlc_count:
        warnings_list.append(f"high is below low in {inverted_ohlc_count} rows")

    consistency_columns = [
        column
        for column in dict.fromkeys(
            (
                "date",
                "ticker",
                "close_adj",
                "close",
                "return_1d",
                "next_period_return",
                "benchmark_close",
                "benchmark_return",
                "benchmark_next_period_return",
                "adj_factor",
                "open",
                "high",
                "low",
                "vwap",
                *ADJUSTED_PRICE_COLUMN_PAIRS,
            )
        )
        if column in schema_names
    ]
    consistency_frame = (
        _parquet_narrow_frame(file_path, consistency_columns)
        if consistency_columns
        else pd.DataFrame()
    )
    derived_returns = (
        _derive_return_consistency(consistency_frame, schema_names)
        if not consistency_frame.empty
        else {"checked": False, "status": "ok", "errors": [], "warnings": []}
    )
    adjusted_prices = (
        _derive_adjusted_price_consistency(consistency_frame, schema_names)
        if not consistency_frame.empty
        else {"checked": False, "status": "ok", "errors": [], "warnings": []}
    )
    errors.extend(derived_returns.get("errors", []))
    errors.extend(adjusted_prices.get("errors", []))
    warnings_list.extend(derived_returns.get("warnings", []))
    warnings_list.extend(adjusted_prices.get("warnings", []))

    return {
        "status": _quality_status(errors),
        "path": str(file_path),
        "exists": True,
        "file_size": file_path.stat().st_size,
        "format": "parquet",
        "rows": int(rows),
        "columns": int(len(schema_names)),
        "row_groups": int(parquet_file.metadata.num_row_groups),
        "date_min": _date_text(date_min),
        "date_max": _date_text(date_max),
        "date_count": int(len(date_values)),
        "ticker_count": int(len(ticker_values)),
        "duplicate_key_count": int(adjacent_duplicate_count),
        "duplicate_check_exact": duplicate_check_exact,
        "out_of_order_count": int(out_of_order_count),
        "invalid_date_count": int(invalid_date_count),
        "missing_ticker_count": int(missing_ticker_count),
        "missing_required_columns": list(missing_required),
        "null_counts": null_counts,
        "null_rates": null_rates,
        "non_positive_price_counts": non_positive_price_counts,
        "negative_volume_count": int(negative_volume_count),
        "inverted_ohlc_count": int(inverted_ohlc_count),
        "derived_return_checks": derived_returns,
        "adjusted_price_checks": adjusted_prices,
        "errors": errors,
        "warnings": warnings_list,
    }


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
