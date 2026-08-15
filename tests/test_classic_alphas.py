from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from moneytree.cli.classic_alphas import build_parser, run_generation
from moneytree.factors.classic import (
    ClassicAlphaContext,
    build_alpha101_features,
    build_alpha191_features,
    build_classic_alpha_features,
)


def _panel(days: int = 120, tickers: list[str] | None = None) -> pd.DataFrame:
    tickers = tickers or ["000001.SZ", "600000.SH", "000002.SZ"]
    dates = pd.date_range("2021-01-04", periods=days, freq="B")
    rows: list[dict[str, object]] = []
    rng = np.random.default_rng(7)
    for idx, ticker in enumerate(tickers):
        base = 10.0 + idx * 2.0
        for date in dates:
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "open": base + 0.1 * rng.standard_normal(),
                    "high": base + 0.3,
                    "low": base - 0.2,
                    "close": base + 0.1 * rng.standard_normal(),
                    "vwap": base + 0.05,
                    "volume": 1_000_000.0 + idx * 100_000.0 + rng.integers(0, 10_000),
                    "amount": 1.0e7 + idx * 1.0e6,
                    "turnover_rate": 1.0 + idx * 0.1,
                    "circ_mv": 1.0e10 + idx * 1.0e9,
                    "industry": "bank",
                }
            )
    return pd.DataFrame(rows)


def test_classic_alpha_column_contracts() -> None:
    panel = _panel(days=60)

    alpha191 = build_alpha191_features(panel)
    alpha101 = build_alpha101_features(panel)

    assert list(alpha191.columns) == [f"alpha191_{idx:03d}" for idx in range(1, 192)]
    assert list(alpha101.columns) == [f"alpha101_{idx:03d}" for idx in range(1, 102)]
    assert alpha191.index.names == ["date", "ticker"]
    assert str(alpha191.dtypes.unique()[0]) == "float32"
    assert not alpha191.isna().all().all()

    combined = build_classic_alpha_features(panel, ["alpha101", "alpha191"])
    assert combined.shape[1] == 292


def test_classic_alpha_unsupported_family_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported classic alpha family"):
        build_classic_alpha_features(_panel(days=10), ["alpha158"])


def test_cross_sectional_rank_is_per_date() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-04", "2021-01-04", "2021-01-04", "2021-01-05", "2021-01-05", "2021-01-05"]),
            "ticker": ["A", "B", "C", "A", "B", "C"],
            "volume": [300.0, 100.0, 200.0, 100.0, 200.0, 300.0],
        }
    )
    frame = frame.set_index(["date", "ticker"])
    context = ClassicAlphaContext(frame)

    ranked = context._rank(context._d["volume"])

    # Highest volume on each date must rank 1.0 within that date cross-section.
    assert float(ranked.loc[("2021-01-04", "A")]) == 1.0
    assert float(ranked.loc[("2021-01-04", "B")]) == pytest.approx(1 / 3)
    assert float(ranked.loc[("2021-01-05", "A")]) == pytest.approx(1 / 3)
    assert float(ranked.loc[("2021-01-05", "C")]) == 1.0


def test_cross_sectional_rank_surfaces_into_alpha191_180() -> None:
    panel = _panel(days=20, tickers=["A", "B"])
    panel.loc[panel["ticker"] == "A", "volume"] = 5000.0
    panel.loc[panel["ticker"] == "B", "volume"] = 1000.0

    alpha191 = build_alpha191_features(panel)

    last_date = alpha191.index.get_level_values("date").max()
    slice_ = alpha191.loc[last_date, "alpha191_180"]
    assert float(slice_.loc["A"]) == 1.0
    assert float(slice_.loc["B"]) == pytest.approx(0.5)


def test_classic_alphas_cli_wide_output(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    _panel(days=40).to_parquet(panel_path)
    output_path = tmp_path / "merged.parquet"

    args = build_parser().parse_args(
        [
            "--input",
            str(panel_path),
            "--output",
            str(output_path),
            "--alpha101",
            "--alpha191",
            "--factor-dtype",
            "float32",
        ]
    )
    result = run_generation(args)

    assert result.rows == 120
    assert result.alpha_columns == 292
    assert output_path.exists()
    assert result.manifest_path is not None and result.manifest_path.exists()

    merged = pd.read_parquet(output_path)
    assert "alpha101_001" in merged.columns
    assert "alpha191_191" in merged.columns


def test_classic_alphas_cli_factor_store(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    _panel(days=40).to_parquet(panel_path)
    store_dir = tmp_path / "store"

    args = build_parser().parse_args(
        [
            "--input",
            str(panel_path),
            "--factor-store-output",
            str(store_dir),
            "--no-wide-output",
            "--alpha101",
            "--factor-dtype",
            "float32",
        ]
    )
    result = run_generation(args)

    manifest_path = store_dir / "manifest.json"
    assert result.factor_store_manifest_path == manifest_path
    assert manifest_path.exists()
    manifest = pd.read_json(manifest_path, typ="series")
    assert manifest["external_generation"]["source"] == "python"
    assert (store_dir / "factors" / "alpha101" / "part-0001.parquet").exists()
