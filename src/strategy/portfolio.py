from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PortfolioConfig:
    # Signal processing
    min_score: float = 0.05
    winsor_z: float = 3.0
    use_prob_signal: bool = True

    # Portfolio constraints
    gross_target: float = 1.0
    net_target: float = 0.0
    max_name_weight: float = 0.02
    min_names_per_side: int = 5

    # Risk scaling
    use_vol_scaling: bool = True
    vol_floor: float = 1e-4
    vol_power: float = 1.0
    min_vol_obs: int = 8

    # Optional coarse sector neutrality
    sector_neutral: bool = False
    sector_prefix: str = "SP_sector_code_"


def build_signal_scores(
    predictions: np.ndarray,
    probs: np.ndarray | None,
    classes_: np.ndarray | None,
    use_prob_signal: bool,
) -> np.ndarray:
    """Build continuous raw scores from class probabilities when available."""
    if use_prob_signal and probs is not None and classes_ is not None:
        class_to_col = {int(cls): i for i, cls in enumerate(classes_)}
        p_pos = probs[:, class_to_col[1]] if 1 in class_to_col else np.zeros(len(predictions))
        p_neg = probs[:, class_to_col[-1]] if -1 in class_to_col else np.zeros(len(predictions))
        return p_pos - p_neg
    return predictions.astype(float)


def _to_name_series(values: np.ndarray, sample_index: pd.Index, name: str) -> pd.Series:
    series = pd.Series(values, index=sample_index, dtype=float, name=name)
    if isinstance(series.index, pd.MultiIndex) and "ticker" in series.index.names:
        series = series.groupby(level="ticker", sort=False).last()
    return series


def _zscore_clip(signal: pd.Series, zmax: float) -> pd.Series:
    if signal.empty:
        return signal.copy()
    mean = float(signal.mean())
    std = float(signal.std(ddof=0))
    if not np.isfinite(std) or std <= 0:
        return pd.Series(0.0, index=signal.index, name=signal.name)
    zscore = (signal - mean) / std
    return zscore.clip(-zmax, zmax)


def _build_vol_map_from_train(
    train_frame: pd.DataFrame,
    return_col: str = "next_period_return",
    min_obs: int = 8,
) -> pd.Series:
    """Estimate ticker-level volatility from the train window only."""
    if return_col not in train_frame.columns:
        return pd.Series(dtype=float, name="vol")

    if isinstance(train_frame.index, pd.MultiIndex) and "ticker" in train_frame.index.names:
        grouped = train_frame[return_col].groupby(level="ticker")
        vol = grouped.std(ddof=0)
        obs = grouped.count()
        vol = vol.where(obs >= min_obs)
    else:
        vol = pd.Series(dtype=float, name="vol")

    vol = vol.replace([np.inf, -np.inf], np.nan)
    vol.name = "vol"
    return vol


def _infer_sector_labels(
    frame_slice: pd.DataFrame,
    sample_index: pd.Index,
    sector_prefix: str,
) -> pd.Series | None:
    sector_cols = [col for col in frame_slice.columns if col.startswith(sector_prefix)]
    if not sector_cols:
        return None
    if not isinstance(sample_index, pd.MultiIndex):
        return None

    subset = frame_slice.loc[sample_index, sector_cols].copy()
    if "ticker" not in subset.index.names:
        return None

    by_ticker = subset.groupby(level="ticker", sort=False).last()
    row_sum = by_ticker.sum(axis=1)
    valid = row_sum > 0
    if not valid.any():
        return None

    labels = pd.Series(index=by_ticker.index, dtype="object", name="sector")
    labels.loc[valid] = by_ticker.loc[valid].idxmax(axis=1)
    return labels


def _neutralize_by_group(weights: pd.Series, groups: pd.Series | None) -> pd.Series:
    if groups is None or weights.empty:
        return weights

    aligned_groups = groups.reindex(weights.index)
    valid = aligned_groups.notna()
    if not valid.any():
        return weights

    out = weights.copy()
    valid_weights = out.loc[valid]
    valid_groups = aligned_groups.loc[valid]
    out.loc[valid] = valid_weights - valid_weights.groupby(valid_groups).transform("mean")
    return out


def _cap_and_redistribute_one_side(
    scores: pd.Series,
    target_sum: float,
    max_weight: float,
    tol: float = 1e-10,
    max_iter: int = 50,
) -> pd.Series:
    """Allocate one side (long or short) under a per-name cap."""
    if scores.empty or target_sum <= 0:
        return pd.Series(0.0, index=scores.index, dtype=float)

    clipped_scores = scores.clip(lower=0)
    if float(clipped_scores.sum()) <= 0:
        return pd.Series(0.0, index=clipped_scores.index, dtype=float)

    weights = pd.Series(0.0, index=clipped_scores.index, dtype=float)
    remaining = float(target_sum)
    free_names = clipped_scores.index.copy()

    for _ in range(max_iter):
        if remaining <= tol or len(free_names) == 0:
            break

        free_scores = clipped_scores.loc[free_names]
        denom = float(free_scores.sum())
        if denom <= 0:
            break

        proposal = remaining * free_scores / denom
        hit_cap = proposal >= (max_weight - tol)
        if hit_cap.any():
            capped = proposal.index[hit_cap]
            weights.loc[capped] = max_weight
            remaining = target_sum - float(weights.sum())
            free_names = free_names.difference(capped)
            continue

        weights.loc[free_names] = proposal
        remaining = target_sum - float(weights.sum())
        break

    return weights.clip(lower=0, upper=max_weight)


def build_portfolio_weights(
    *,
    predictions: np.ndarray,
    probs: np.ndarray | None,
    classes_: np.ndarray | None,
    sample_index: pd.Index,
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    cfg: PortfolioConfig,
) -> pd.Series:
    """Build ticker-level long/short weights from model outputs."""
    if len(predictions) != len(sample_index):
        raise ValueError("predictions and sample_index must have equal length.")

    raw_scores = build_signal_scores(
        predictions=predictions,
        probs=probs,
        classes_=classes_,
        use_prob_signal=cfg.use_prob_signal,
    )
    score = _to_name_series(raw_scores, sample_index=sample_index, name="score")

    score = score.where(score.abs() >= cfg.min_score, 0.0)
    active = score[score != 0]
    if active.empty:
        return pd.Series(dtype=float, name="weight")

    zscores = _zscore_clip(active, zmax=cfg.winsor_z)

    if cfg.use_vol_scaling:
        vol_map = _build_vol_map_from_train(
            train_frame=train_frame,
            return_col="next_period_return",
            min_obs=cfg.min_vol_obs,
        )
        vol = vol_map.reindex(zscores.index)
        fallback_vol = float(np.nanmedian(vol_map.to_numpy())) if not vol_map.empty else float("nan")
        if not np.isfinite(fallback_vol):
            fallback_vol = 0.20
        vol = vol.fillna(fallback_vol).clip(lower=cfg.vol_floor)
        risk_scale = 1.0 / np.power(vol, cfg.vol_power)
        zscores = zscores * risk_scale

    if cfg.sector_neutral:
        sector_labels = _infer_sector_labels(
            frame_slice=test_frame,
            sample_index=sample_index,
            sector_prefix=cfg.sector_prefix,
        )
        zscores = _neutralize_by_group(zscores, sector_labels)

    zscores = zscores.where(zscores.abs() > 1e-12, 0.0)
    zscores = zscores[zscores != 0]
    if zscores.empty:
        return pd.Series(dtype=float, name="weight")

    long_scores = zscores[zscores > 0]
    short_scores = (-zscores[zscores < 0])

    if len(long_scores) < cfg.min_names_per_side:
        long_scores = pd.Series(dtype=float)
    if len(short_scores) < cfg.min_names_per_side:
        short_scores = pd.Series(dtype=float)

    gross_target = max(float(cfg.gross_target), 0.0)
    net_target = float(np.clip(cfg.net_target, -gross_target, gross_target))
    max_name_weight = max(float(cfg.max_name_weight), 0.0)

    raw_long_target = max(0.0, 0.5 * (gross_target + net_target))
    raw_short_target = max(0.0, 0.5 * (gross_target - net_target))
    long_target = raw_long_target
    short_target = raw_short_target

    if long_scores.empty and short_scores.empty:
        return pd.Series(dtype=float, name="weight")
    if long_scores.empty:
        long_target = 0.0
        short_target = min(gross_target, raw_long_target + raw_short_target)
    elif short_scores.empty:
        short_target = 0.0
        long_target = min(gross_target, raw_long_target + raw_short_target)

    long_weights = _cap_and_redistribute_one_side(
        scores=long_scores,
        target_sum=long_target,
        max_weight=max_name_weight,
    )
    short_weights = _cap_and_redistribute_one_side(
        scores=short_scores,
        target_sum=short_target,
        max_weight=max_name_weight,
    )

    weights = pd.concat([long_weights, -short_weights]).sort_index()
    weights.name = "weight"
    return weights


def estimate_turnover_from_weights(
    current_weights: pd.Series,
    previous_weights: pd.Series | None = None,
) -> float:
    """Estimate one-way turnover as 0.5 * sum(|w_t - w_{t-1}|)."""
    if current_weights.empty:
        return 0.0 if previous_weights is None else float(0.5 * previous_weights.abs().sum())

    if previous_weights is None or previous_weights.empty:
        return float(0.5 * current_weights.abs().sum())

    union_index = current_weights.index.union(previous_weights.index)
    current_aligned = current_weights.reindex(union_index, fill_value=0.0)
    previous_aligned = previous_weights.reindex(union_index, fill_value=0.0)
    return float(0.5 * (current_aligned - previous_aligned).abs().sum())


def compute_period_return_from_weights(
    weights: pd.Series,
    realized_returns: np.ndarray,
    sample_index: pd.Index,
    cost_bps: float = 0.0,
    previous_weights: pd.Series | None = None,
) -> tuple[float, pd.Series, float]:
    """Compute period return from ticker-level weights and realized returns."""
    if len(realized_returns) != len(sample_index):
        raise ValueError("realized_returns and sample_index must have equal length.")

    name_returns = _to_name_series(realized_returns, sample_index=sample_index, name="realized_return")
    turnover = estimate_turnover_from_weights(weights, previous_weights=previous_weights)
    if weights.empty:
        cost = (cost_bps / 10000.0) * turnover
        return float(-cost), weights, turnover

    aligned_returns = name_returns.reindex(weights.index).fillna(0.0)
    gross_return = float((weights * aligned_returns).sum())
    cost = (cost_bps / 10000.0) * turnover
    return float(gross_return - cost), weights, float(turnover)
