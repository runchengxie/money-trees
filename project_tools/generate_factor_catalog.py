from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "factor-catalog.csv"

FIELDNAMES = [
    "family",
    "column",
    "group",
    "count_scope",
    "input_fields",
    "formula_status",
    "formula_source",
    "formula_or_rule",
    "generation",
    "notes",
]


def _classic_alpha101_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for idx in range(1, 102):
        rows.append(
            {
                "family": "alpha101",
                "column": f"alpha101_{idx:03d}",
                "group": "classic_formula",
                "count_scope": "101",
                "input_fields": "open, high, low, close, volume, vwap, returns",
                "formula_status": "implemented_local",
                "formula_source": "src/moneytree/factors/classic.py",
                "formula_or_rule": (
                    f"WQAlpha{idx} implemented in Python with cross-sectional "
                    "rank/scale (grouped by trade date)."
                ),
                "generation": "moneytree.factors.classic.build_alpha101_features",
                "notes": (
                    "Ported from the wu-alpha191-alpha101 reference repository with "
                    "cross-sectional rank/scale semantics. The DolphinDB external path "
                    "remains an alternative generation route with different rank/scale and "
                    "missing-value semantics; compare outputs before production use."
                ),
            }
        )
    return rows


def _classic_alpha191_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for idx in range(1, 192):
        rows.append(
            {
                "family": "alpha191",
                "column": f"alpha191_{idx:03d}",
                "group": "classic_formula",
                "count_scope": "191",
                "input_fields": "open, high, low, close, volume, vwap, returns, amount, turnover_rate",
                "formula_status": "implemented_local",
                "formula_source": "src/moneytree/factors/classic.py",
                "formula_or_rule": (
                    f"GTJA Alpha{idx} implemented in Python with cross-sectional "
                    "rank/scale (grouped by trade date)."
                ),
                "generation": "moneytree.factors.classic.build_alpha191_features",
                "notes": (
                    "Ported from the wu-alpha191-alpha101 reference repository with "
                    "cross-sectional rank/scale semantics. The DolphinDB external path "
                    "remains an alternative generation route with different SMA, DECAYLINEAR, "
                    "suspension, limit-hit, and missing-value semantics; compare outputs "
                    "before production use."
                ),
            }
        )
    return rows


def _local_row(
    *,
    family: str,
    column: str,
    group: str,
    count_scope: int,
    input_fields: str,
    formula_or_rule: str,
    notes: str,
) -> dict[str, str]:
    return {
        "family": family,
        "column": column,
        "group": group,
        "count_scope": str(count_scope),
        "input_fields": input_fields,
        "formula_status": "implemented_local",
        "formula_source": "src/moneytree/factors/qlib.py",
        "formula_or_rule": formula_or_rule,
        "generation": f"moneytree.factors.qlib.build_{family}_features",
        "notes": notes,
    }


def _alpha158_rows() -> list[dict[str, str]]:
    prefix = "alpha158"
    rows: list[dict[str, str]] = []
    candlesticks = [
        ("kmid", "open, close", "(close - open) / open", "Daily body return."),
        ("klen", "open, high, low", "(high - low) / open", "Daily range normalized by open."),
        (
            "kmid2",
            "open, high, low, close",
            "(close - open) / (high - low)",
            "Daily body normalized by high-low range.",
        ),
        (
            "kup",
            "open, high, close",
            "(high - max(open, close)) / open",
            "Upper shadow normalized by open.",
        ),
        (
            "kup2",
            "open, high, low, close",
            "(high - max(open, close)) / (high - low)",
            "Upper shadow normalized by high-low range.",
        ),
        (
            "klow",
            "open, low, close",
            "(min(open, close) - low) / open",
            "Lower shadow normalized by open.",
        ),
        (
            "klow2",
            "open, high, low, close",
            "(min(open, close) - low) / (high - low)",
            "Lower shadow normalized by high-low range.",
        ),
        (
            "ksft",
            "open, high, low, close",
            "(2 * close - high - low) / open",
            "Close location relative to daily range, normalized by open.",
        ),
        (
            "ksft2",
            "high, low, close",
            "(2 * close - high - low) / (high - low)",
            "Close location relative to daily range.",
        ),
    ]
    for suffix, input_fields, formula, notes in candlesticks:
        rows.append(
            _local_row(
                family=prefix,
                column=f"{prefix}_{suffix}",
                group="candlestick",
                count_scope=158,
                input_fields=input_fields,
                formula_or_rule=formula,
                notes=notes,
            )
        )

    for field in ("open", "high", "low", "vwap"):
        for lag in range(20):
            rows.append(
                _local_row(
                    family=prefix,
                    column=f"{prefix}_{field}_lag{lag:02d}_rel_close",
                    group="price_lag",
                    count_scope=158,
                    input_fields=f"{field}, close",
                    formula_or_rule=f"shift({field}, {lag}) / current_close - 1",
                    notes="Price-like fields use adjusted columns when adjusted=True.",
                )
            )

    rolling_specs = [
        ("roc", "close", "close / shift(close, {window}) - 1", "Window return."),
        ("ma", "close", "rolling_mean(close, {window}) / close - 1", "Moving average gap."),
        ("std", "close", "rolling_std(pct_change(close, 1), {window})", "Return volatility."),
        ("max", "high, close", "rolling_max(high, {window}) / close - 1", "High breakout gap."),
        ("min", "low, close", "rolling_min(low, {window}) / close - 1", "Low breakdown gap."),
        (
            "q80",
            "close",
            "rolling_quantile(close, {window}, 0.8) / close - 1",
            "Upper rolling quantile gap.",
        ),
        (
            "q20",
            "close",
            "rolling_quantile(close, {window}, 0.2) / close - 1",
            "Lower rolling quantile gap.",
        ),
        ("rank", "close", "rank_pct_latest(close over {window})", "Latest close percentile rank."),
        (
            "rsv",
            "high, low, close",
            "(close - rolling_min(low, {window})) / (rolling_max(high, {window}) - rolling_min(low, {window}))",
            "Close position inside rolling high-low range.",
        ),
        (
            "ret_mean",
            "close",
            "rolling_mean(pct_change(close, 1), {window})",
            "Rolling mean daily return.",
        ),
        (
            "vma",
            "volume",
            "volume / rolling_mean(volume, {window}) - 1",
            "Volume relative to moving average.",
        ),
        (
            "vstd",
            "volume",
            "rolling_std(pct_change(volume, 1), {window})",
            "Volume-change volatility.",
        ),
        (
            "amount_ma",
            "amount",
            "amount / rolling_mean(amount, {window}) - 1",
            "Amount relative to moving average; amount falls back to close * volume if missing.",
        ),
    ]
    for window in (5, 10, 20, 30, 60):
        for suffix, input_fields, formula_template, notes in rolling_specs:
            rows.append(
                _local_row(
                    family=prefix,
                    column=f"{prefix}_{suffix}_{window}",
                    group="rolling_window",
                    count_scope=158,
                    input_fields=input_fields,
                    formula_or_rule=formula_template.format(window=window),
                    notes=notes,
                )
            )

    extras = [
        ("vwap_rel_close", "vwap, close", "vwap / close - 1", "VWAP gap to close."),
        ("high_low_spread", "high, low, close", "(high - low) / close", "Daily spread normalized by close."),
        ("close_to_high", "close, high", "close / high - 1", "Close gap to high."),
        ("close_to_low", "close, low", "close / low - 1", "Close gap to low."),
    ]
    for suffix, input_fields, formula, notes in extras:
        rows.append(
            _local_row(
                family=prefix,
                column=f"{prefix}_{suffix}",
                group="misc_price_volume",
                count_scope=158,
                input_fields=input_fields,
                formula_or_rule=formula,
                notes=notes,
            )
        )

    if len(rows) != 158:
        raise RuntimeError(f"Generated {len(rows)} Alpha158 rows; expected 158.")
    return rows


def _alpha360_rows() -> list[dict[str, str]]:
    prefix = "alpha360"
    rows: list[dict[str, str]] = []
    for field in ("open", "high", "low", "close", "vwap", "volume"):
        for lag in range(60):
            if field == "volume":
                input_fields = "volume"
                formula = f"shift(volume, {lag}) / current_volume - 1"
                notes = "Volume is always raw volume, not adjusted."
            else:
                input_fields = f"{field}, close"
                formula = f"shift({field}, {lag}) / current_close - 1"
                notes = "Price-like fields use adjusted columns when adjusted=True."
            rows.append(
                _local_row(
                    family=prefix,
                    column=f"{prefix}_{field}_lag{lag:02d}",
                    group="sequence_lag",
                    count_scope=360,
                    input_fields=input_fields,
                    formula_or_rule=formula,
                    notes=notes,
                )
            )
    if len(rows) != 360:
        raise RuntimeError(f"Generated {len(rows)} Alpha360 rows; expected 360.")
    return rows


def build_rows() -> list[dict[str, str]]:
    rows = [
        *_classic_alpha101_rows(),
        *_classic_alpha191_rows(),
        *_alpha158_rows(),
        *_alpha360_rows(),
    ]
    if len(rows) != 810:
        raise RuntimeError(f"Generated {len(rows)} factor catalog rows; expected 810.")
    return rows


def main() -> None:
    rows = build_rows()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
