from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.portfolio import (
    PortfolioConfig,
    build_portfolio_weights,
    build_signal_scores,
    compute_period_return_from_weights,
)


def _build_train_frame_for_tickers(tickers: list[str]) -> pd.DataFrame:
    train_idx = pd.MultiIndex.from_product(
        [
            pd.to_datetime(["2020-09-30", "2020-12-31"]),
            tickers,
        ],
        names=["date", "ticker"],
    )
    returns = np.linspace(0.005, 0.025, num=len(train_idx))
    return pd.DataFrame({"next_period_return": returns}, index=train_idx)


def test_build_signal_scores_respects_classes_mapping() -> None:
    preds = np.array([1, -1, 0])
    probs = np.array(
        [
            [0.15, 0.70, 0.15],
            [0.65, 0.20, 0.15],
            [0.20, 0.20, 0.60],
        ]
    )
    classes = np.array([-1, 1, 0])

    scores = build_signal_scores(
        predictions=preds,
        probs=probs,
        classes_=classes,
        use_prob_signal=True,
    )

    expected = np.array([0.55, -0.45, 0.00])
    assert np.allclose(scores, expected)


def test_build_portfolio_weights_respects_caps_and_exposure() -> None:
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-03-31"), "B"),
            (pd.Timestamp("2021-03-31"), "C"),
            (pd.Timestamp("2021-03-31"), "D"),
            (pd.Timestamp("2021-03-31"), "E"),
            (pd.Timestamp("2021-03-31"), "F"),
        ],
        names=["date", "ticker"],
    )
    train_idx = pd.MultiIndex.from_product(
        [
            pd.to_datetime(["2020-09-30", "2020-12-31"]),
            ["A", "B", "C", "D", "E", "F"],
        ],
        names=["date", "ticker"],
    )
    train_frame = pd.DataFrame(
        {
            "next_period_return": np.array(
                [0.01, 0.02, -0.01, -0.02, 0.015, -0.005, 0.012, 0.018, -0.012, -0.016, 0.014, -0.004]
            )
        },
        index=train_idx,
    )
    test_frame = pd.DataFrame({"f": np.arange(len(idx), dtype=float)}, index=idx)

    preds = np.array([1, 1, 1, -1, -1, -1])
    cfg = PortfolioConfig(
        min_score=0.0,
        winsor_z=3.0,
        use_prob_signal=False,
        gross_target=1.0,
        net_target=0.0,
        max_name_weight=0.25,
        min_names_per_side=1,
        use_vol_scaling=False,
    )

    weights = build_portfolio_weights(
        predictions=preds,
        probs=None,
        classes_=None,
        sample_index=idx,
        train_frame=train_frame,
        test_frame=test_frame,
        cfg=cfg,
    )

    assert len(weights) == 6
    assert float(weights.abs().max()) <= 0.25 + 1e-12
    assert np.isclose(float(weights.abs().sum()), 1.0)
    assert np.isclose(float(weights.sum()), 0.0)


def test_compute_period_return_from_weights_matches_expected() -> None:
    weights = pd.Series({"A": 0.5, "B": -0.5}, dtype=float)
    prev = pd.Series({"A": 0.25, "B": -0.25}, dtype=float)
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2022-03-31"), "A"),
            (pd.Timestamp("2022-03-31"), "B"),
        ],
        names=["date", "ticker"],
    )
    realized = np.array([0.02, -0.01])

    period_ret, _, turnover = compute_period_return_from_weights(
        weights=weights,
        realized_returns=realized,
        sample_index=idx,
        cost_bps=10.0,
        previous_weights=prev,
    )

    expected_gross = 0.5 * 0.02 + (-0.5) * (-0.01)
    expected_turnover = 0.5 * (abs(0.5 - 0.25) + abs(-0.5 - (-0.25)))
    expected_net = expected_gross - (10.0 / 10000.0) * expected_turnover

    assert np.isclose(turnover, expected_turnover)
    assert np.isclose(period_ret, expected_net)


def test_build_portfolio_weights_redistributes_to_single_side_when_other_side_too_small() -> None:
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-03-31"), "B"),
            (pd.Timestamp("2021-03-31"), "C"),
            (pd.Timestamp("2021-03-31"), "D"),
        ],
        names=["date", "ticker"],
    )
    preds = np.array([1, 1, 1, -1], dtype=int)
    train_frame = _build_train_frame_for_tickers(["A", "B", "C", "D"])
    test_frame = pd.DataFrame({"f": np.arange(len(idx), dtype=float)}, index=idx)
    cfg = PortfolioConfig(
        min_score=0.0,
        winsor_z=3.0,
        use_prob_signal=False,
        gross_target=1.0,
        net_target=0.0,
        max_name_weight=1.0,
        min_names_per_side=2,
        use_vol_scaling=False,
    )

    weights = build_portfolio_weights(
        predictions=preds,
        probs=None,
        classes_=None,
        sample_index=idx,
        train_frame=train_frame,
        test_frame=test_frame,
        cfg=cfg,
    )

    assert not weights.empty
    assert (weights > 0).all()
    assert np.isclose(float(weights.sum()), 1.0)
    assert np.isclose(float(weights.abs().sum()), 1.0)


def test_build_portfolio_weights_sector_neutral_without_sector_columns_matches_baseline() -> None:
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-03-31"), "B"),
            (pd.Timestamp("2021-03-31"), "C"),
            (pd.Timestamp("2021-03-31"), "D"),
        ],
        names=["date", "ticker"],
    )
    preds = np.array([1, 1, -1, -1], dtype=int)
    train_frame = _build_train_frame_for_tickers(["A", "B", "C", "D"])
    test_frame = pd.DataFrame({"f": np.arange(len(idx), dtype=float)}, index=idx)
    base_cfg = PortfolioConfig(
        min_score=0.0,
        winsor_z=3.0,
        use_prob_signal=False,
        gross_target=1.0,
        net_target=0.0,
        max_name_weight=0.6,
        min_names_per_side=1,
        use_vol_scaling=False,
        sector_neutral=False,
    )
    neutral_cfg = PortfolioConfig(
        min_score=0.0,
        winsor_z=3.0,
        use_prob_signal=False,
        gross_target=1.0,
        net_target=0.0,
        max_name_weight=0.6,
        min_names_per_side=1,
        use_vol_scaling=False,
        sector_neutral=True,
    )

    base_weights = build_portfolio_weights(
        predictions=preds,
        probs=None,
        classes_=None,
        sample_index=idx,
        train_frame=train_frame,
        test_frame=test_frame,
        cfg=base_cfg,
    )
    neutral_weights = build_portfolio_weights(
        predictions=preds,
        probs=None,
        classes_=None,
        sample_index=idx,
        train_frame=train_frame,
        test_frame=test_frame,
        cfg=neutral_cfg,
    )

    pd.testing.assert_series_equal(base_weights, neutral_weights)


def test_build_portfolio_weights_duplicate_ticker_uses_last_observation() -> None:
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-03-31"), "B"),
        ],
        names=["date", "ticker"],
    )
    preds = np.array([1, -1, 1], dtype=int)
    train_frame = _build_train_frame_for_tickers(["A", "B"])
    test_frame = pd.DataFrame({"f": [1.0, 2.0, 3.0]}, index=idx)
    cfg = PortfolioConfig(
        min_score=0.0,
        winsor_z=3.0,
        use_prob_signal=False,
        gross_target=1.0,
        net_target=0.0,
        max_name_weight=1.0,
        min_names_per_side=1,
        use_vol_scaling=False,
    )

    weights = build_portfolio_weights(
        predictions=preds,
        probs=None,
        classes_=None,
        sample_index=idx,
        train_frame=train_frame,
        test_frame=test_frame,
        cfg=cfg,
    )

    assert set(weights.index.tolist()) == {"A", "B"}
    assert float(weights.loc["A"]) < 0.0
    assert float(weights.loc["B"]) > 0.0


def test_build_portfolio_weights_cap_can_limit_total_allocated_exposure() -> None:
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-03-31"), "B"),
            (pd.Timestamp("2021-03-31"), "C"),
            (pd.Timestamp("2021-03-31"), "D"),
        ],
        names=["date", "ticker"],
    )
    preds = np.array([1, 1, 1, -1], dtype=int)
    train_frame = _build_train_frame_for_tickers(["A", "B", "C", "D"])
    test_frame = pd.DataFrame({"f": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    cfg = PortfolioConfig(
        min_score=0.0,
        winsor_z=3.0,
        use_prob_signal=False,
        gross_target=1.0,
        net_target=0.0,
        max_name_weight=0.2,
        min_names_per_side=2,
        use_vol_scaling=False,
    )

    weights = build_portfolio_weights(
        predictions=preds,
        probs=None,
        classes_=None,
        sample_index=idx,
        train_frame=train_frame,
        test_frame=test_frame,
        cfg=cfg,
    )

    assert np.isclose(float(weights.abs().sum()), 0.6)
    assert float(weights.abs().max()) <= 0.2 + 1e-12


def test_build_portfolio_weights_signal_risk_qp_respects_constraints() -> None:
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-03-31"), "B"),
            (pd.Timestamp("2021-03-31"), "C"),
            (pd.Timestamp("2021-03-31"), "D"),
            (pd.Timestamp("2021-03-31"), "E"),
            (pd.Timestamp("2021-03-31"), "F"),
        ],
        names=["date", "ticker"],
    )
    train_idx = pd.MultiIndex.from_product(
        [
            pd.to_datetime(
                ["2020-06-30", "2020-09-30", "2020-12-31", "2021-03-31"],
            ),
            ["A", "B", "C", "D", "E", "F"],
        ],
        names=["date", "ticker"],
    )
    train_frame = pd.DataFrame(
        {
            "next_period_return": np.array(
                [
                    0.01,
                    0.02,
                    0.00,
                    -0.01,
                    -0.02,
                    0.005,
                    0.015,
                    0.01,
                    -0.005,
                    -0.015,
                    -0.02,
                    0.004,
                    0.012,
                    0.018,
                    -0.01,
                    -0.02,
                    -0.015,
                    0.003,
                    0.02,
                    0.017,
                    -0.012,
                    -0.016,
                    -0.01,
                    0.002,
                ]
            )
        },
        index=train_idx,
    )
    test_frame = pd.DataFrame({"f": np.arange(len(idx), dtype=float)}, index=idx)
    preds = np.array([1, 1, 1, -1, -1, -1], dtype=int)

    cfg = PortfolioConfig(
        min_score=0.0,
        winsor_z=3.0,
        use_prob_signal=False,
        weighting_method="signal_risk_qp",
        gross_target=1.0,
        net_target=0.0,
        max_name_weight=0.2,
        min_names_per_side=1,
        use_vol_scaling=False,
        qp_risk_aversion=0.0,
        qp_turnover_penalty=0.0,
        qp_max_names=0,
        qp_solver_max_iter=400,
    )

    weights = build_portfolio_weights(
        predictions=preds,
        probs=None,
        classes_=None,
        sample_index=idx,
        train_frame=train_frame,
        test_frame=test_frame,
        cfg=cfg,
        previous_weights=None,
    )

    assert not weights.empty
    assert float(weights.abs().max()) <= 0.2 + 1e-8
    assert float(weights.abs().sum()) <= 1.0 + 1e-6
    assert abs(float(weights.sum())) <= 1e-4


def test_signal_risk_qp_high_turnover_penalty_tracks_previous_weights() -> None:
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2021-03-31"), "A"),
            (pd.Timestamp("2021-03-31"), "B"),
            (pd.Timestamp("2021-03-31"), "C"),
            (pd.Timestamp("2021-03-31"), "D"),
        ],
        names=["date", "ticker"],
    )
    train_frame = _build_train_frame_for_tickers(["A", "B", "C", "D"])
    test_frame = pd.DataFrame({"f": np.arange(len(idx), dtype=float)}, index=idx)
    preds = np.array([1, -1, 1, -1], dtype=int)
    previous = pd.Series({"A": 0.1, "B": -0.1}, dtype=float)

    cfg = PortfolioConfig(
        min_score=0.0,
        winsor_z=3.0,
        use_prob_signal=False,
        weighting_method="signal_risk_qp",
        gross_target=0.2,
        net_target=0.0,
        max_name_weight=0.2,
        min_names_per_side=1,
        use_vol_scaling=False,
        qp_risk_aversion=0.0,
        qp_turnover_penalty=1e6,
        qp_max_names=0,
        qp_solver_max_iter=400,
    )

    weights = build_portfolio_weights(
        predictions=preds,
        probs=None,
        classes_=None,
        sample_index=idx,
        train_frame=train_frame,
        test_frame=test_frame,
        cfg=cfg,
        previous_weights=previous,
    )
    aligned = weights.reindex(["A", "B", "C", "D"], fill_value=0.0)

    assert np.isclose(float(aligned.loc["A"]), 0.1, atol=1e-3)
    assert np.isclose(float(aligned.loc["B"]), -0.1, atol=1e-3)
    assert abs(float(aligned.loc["C"])) <= 1e-3
    assert abs(float(aligned.loc["D"])) <= 1e-3
