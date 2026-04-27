from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from moneytree.factors import (
    add_factor_family_features,
    build_alpha158_features,
    build_alpha360_features,
    compute_factor_ic,
    get_factor_family,
    summarize_factor_ic,
)
from moneytree.factors.ops import cs_rank, decay_linear
from project_tools.generate_factor_catalog import FIELDNAMES, build_rows


def _panel() -> pd.DataFrame:
    dates = pd.date_range("2021-01-01", periods=80, freq="B")
    tickers = ["000001.SZ", "000002.SZ", "000003.SZ"]
    rows: list[dict[str, object]] = []
    for i, date in enumerate(dates):
        for j, ticker in enumerate(tickers):
            base = 10.0 + i * 0.1 + j
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "open": base,
                    "high": base + 0.3,
                    "low": base - 0.2,
                    "close": base + 0.1 * (j - 1),
                    "vwap": base + 0.05,
                    "volume": 1000.0 + 10.0 * i + 100.0 * j,
                    "amount": (1000.0 + 10.0 * i + 100.0 * j) * (base + 0.05),
                    "next_period_return": 0.001 * (j - 1) + 0.0001 * i,
                }
            )
    return pd.DataFrame(rows).set_index(["date", "ticker"])


def test_build_alpha158_and_alpha360_feature_counts() -> None:
    panel = _panel()

    alpha158 = build_alpha158_features(panel)
    alpha360 = build_alpha360_features(panel)

    assert alpha158.shape == (len(panel), 158)
    assert alpha360.shape == (len(panel), 360)
    assert alpha158.index.equals(panel.index)
    assert alpha360.index.equals(panel.index)
    assert "alpha158_kmid" in alpha158.columns
    assert "alpha360_close_lag00" in alpha360.columns


def test_add_factor_family_features_appends_supported_local_families() -> None:
    panel = _panel()

    out = add_factor_family_features(panel, ["alpha158", "alpha360"])

    assert out.shape[1] == panel.shape[1] + 158 + 360
    assert "alpha158_kmid" in out.columns
    assert "alpha360_volume_lag59" in out.columns


def test_factor_ic_summary() -> None:
    panel = _panel().copy()
    panel["good_factor"] = panel["next_period_return"]
    panel["bad_factor"] = -panel["next_period_return"]

    ic = compute_factor_ic(panel, ["good_factor", "bad_factor"])
    summary = summarize_factor_ic(ic)

    best = summary.iloc[0]
    assert best["factor"] == "good_factor"
    assert best["rank_ic_mean"] > 0


def test_factor_catalog_describes_external_and_local_generation() -> None:
    assert get_factor_family("alpha101").local_generation == "external"
    assert "build_alpha158_features" in get_factor_family("alpha158").local_generation


def test_factor_catalog_csv_is_generated_and_formula_status_is_explicit() -> None:
    catalog_path = Path(__file__).resolve().parents[1] / "docs" / "factor_catalog.csv"
    with catalog_path.open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))

    generated_rows = build_rows()

    assert list(csv_rows[0].keys()) == FIELDNAMES
    assert csv_rows == generated_rows
    assert len(csv_rows) == 810

    alpha101 = next(row for row in csv_rows if row["column"] == "alpha101_001")
    alpha158 = next(row for row in csv_rows if row["column"] == "alpha158_kmid")
    alpha360 = next(row for row in csv_rows if row["column"] == "alpha360_volume_lag59")

    assert alpha101["formula_status"] == "external_not_stored"
    assert "Precompute WQAlpha1" in alpha101["formula_or_rule"]
    assert alpha158["formula_status"] == "implemented_local"
    assert alpha158["formula_or_rule"] == "(close - open) / open"
    assert alpha360["formula_status"] == "implemented_local"
    assert alpha360["formula_or_rule"] == "shift(volume, 59) / current_volume - 1"


def test_ops_rank_and_decay_linear() -> None:
    matrix = pd.DataFrame(
        {
            "A": [1.0, 2.0, 3.0],
            "B": [3.0, 2.0, 1.0],
        },
        index=pd.date_range("2021-01-01", periods=3),
    )

    ranked = cs_rank(matrix)
    decayed = decay_linear(matrix, window=2, min_periods=1)

    assert np.isclose(float(ranked.iloc[0]["A"]), 0.5)
    assert np.isclose(float(ranked.iloc[0]["B"]), 1.0)
    assert np.isclose(float(decayed.iloc[1]["A"]), (1.0 + 2.0 * 2.0) / 3.0)
