from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf


@dataclass
class PortfolioConfig:
    # Signal processing
    min_score: float = 0.05
    winsor_z: float = 3.0
    use_prob_signal: bool = True
    weighting_method: str = "heuristic"  # heuristic | signal_risk_qp

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

    # Signal-risk QP settings
    qp_risk_aversion: float = 10.0
    qp_turnover_penalty: float = 5.0
    qp_cov_lookback: int = 252
    qp_cov_shrinkage: bool = True
    qp_cov_ridge: float = 1e-6
    qp_mu_clip: float = 1.0
    qp_max_names: int = 300
    qp_solver_max_iter: int = 300
    qp_solver_ftol: float = 1e-9
    qp_fallback_to_heuristic: bool = True

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


def _build_heuristic_weights_from_scores(
    zscores: pd.Series,
    cfg: PortfolioConfig,
) -> pd.Series:
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


def _with_portfolio_attrs(
    weights: pd.Series,
    *,
    qp_fallback: bool = False,
) -> pd.Series:
    weights.attrs["qp_fallback"] = bool(qp_fallback)
    return weights


def _build_rank_based_mu(scores: pd.Series, clip_value: float) -> pd.Series:
    if scores.empty:
        return pd.Series(dtype=float, name="mu")

    ranks = scores.rank(method="average", pct=True)
    centered = 2.0 * (ranks - 0.5)
    if np.isfinite(clip_value) and clip_value > 0:
        centered = centered.clip(lower=-clip_value, upper=clip_value)
    centered.name = "mu"
    return centered.astype(float)


def _estimate_covariance_matrix(
    train_frame: pd.DataFrame,
    tickers: pd.Index,
    lookback: int,
    use_shrinkage: bool,
    ridge: float,
    return_col: str = "next_period_return",
) -> np.ndarray:
    n_assets = int(len(tickers))
    if n_assets == 0:
        return np.zeros((0, 0), dtype=float)

    if return_col not in train_frame.columns:
        return np.eye(n_assets, dtype=float) * max(float(ridge), 1e-6)

    if not isinstance(train_frame.index, pd.MultiIndex) or "ticker" not in train_frame.index.names:
        return np.eye(n_assets, dtype=float) * max(float(ridge), 1e-6)

    returns = train_frame[return_col].copy()
    if "date" in returns.index.names and lookback > 0:
        unique_dates = returns.index.get_level_values("date").unique().sort_values()
        if len(unique_dates) > lookback:
            keep_dates = unique_dates[-lookback:]
            date_mask = returns.index.get_level_values("date").isin(keep_dates)
            returns = returns.loc[date_mask]

    pivot = (
        returns.reset_index()[["date", "ticker", return_col]]
        .pivot(index="date", columns="ticker", values=return_col)
        .sort_index()
    )
    pivot = pivot.reindex(columns=tickers)
    if pivot.empty:
        return np.eye(n_assets, dtype=float) * max(float(ridge), 1e-6)

    matrix = pivot.to_numpy(dtype=float)
    col_fill = np.nanmedian(matrix, axis=0)
    col_fill = np.where(np.isfinite(col_fill), col_fill, 0.0)
    bad = ~np.isfinite(matrix)
    if bad.any():
        matrix[bad] = np.take(col_fill, np.where(bad)[1])
    matrix = np.where(np.isfinite(matrix), matrix, 0.0)

    if matrix.shape[0] < 2:
        col_var = np.nanvar(matrix, axis=0)
        col_var = np.where(np.isfinite(col_var) & (col_var > 0), col_var, 1e-4)
        cov = np.diag(col_var)
    elif use_shrinkage:
        try:
            cov = LedoitWolf().fit(matrix).covariance_
        except ValueError:
            cov = np.cov(matrix, rowvar=False, ddof=0)
    else:
        cov = np.cov(matrix, rowvar=False, ddof=0)

    cov = np.asarray(cov, dtype=float)
    if cov.ndim == 0:
        cov = np.array([[float(cov)]], dtype=float)
    if cov.shape != (n_assets, n_assets):
        cov = np.eye(n_assets, dtype=float) * 1e-4

    cov = np.where(np.isfinite(cov), cov, 0.0)
    cov = 0.5 * (cov + cov.T)

    diag = np.diag(cov).copy()
    fallback_var = float(np.nanmedian(diag[diag > 0])) if np.any(diag > 0) else 1e-4
    diag = np.where(diag > 0, diag, fallback_var)
    np.fill_diagonal(cov, diag)

    cov += np.eye(n_assets, dtype=float) * max(float(ridge), 0.0)
    return cov


def _build_qp_initial_guess(
    mu: np.ndarray,
    max_name_weight: float,
    gross_target: float,
    net_target: float,
    previous_weights: np.ndarray | None = None,
) -> np.ndarray:
    n_assets = int(len(mu))
    x0 = np.zeros(2 * n_assets, dtype=float)
    if n_assets == 0 or max_name_weight <= 0:
        return x0

    if previous_weights is not None and len(previous_weights) == n_assets:
        w_prev = np.asarray(previous_weights, dtype=float)
        if np.any(np.abs(w_prev) > 0):
            w_seed = np.clip(w_prev, -max_name_weight, max_name_weight)
            gross = float(np.abs(w_seed).sum())
            if gross > gross_target and gross > 0:
                w_seed *= gross_target / gross
            x0[:n_assets] = np.clip(w_seed, 0.0, max_name_weight)
            x0[n_assets:] = np.clip(-w_seed, 0.0, max_name_weight)
            return x0

    gross_seed = min(float(gross_target), 2.0 * n_assets * max_name_weight)
    if gross_seed <= 0:
        return x0

    long_budget = max(0.0, 0.5 * (gross_seed + net_target))
    short_budget = max(0.0, 0.5 * (gross_seed - net_target))

    long_order = np.argsort(-mu)
    short_order = np.argsort(mu)

    for i in long_order:
        if long_budget <= 1e-12:
            break
        take = min(max_name_weight, long_budget)
        x0[i] = take
        long_budget -= take

    for i in short_order:
        if short_budget <= 1e-12:
            break
        take = min(max_name_weight, short_budget)
        x0[n_assets + i] = take
        short_budget -= take

    gross = float(x0[:n_assets].sum() + x0[n_assets:].sum())
    if gross > gross_target and gross > 0:
        x0 *= gross_target / gross
    return x0


def _solve_signal_risk_qp_weights(
    *,
    signal_scores: pd.Series,
    train_frame: pd.DataFrame,
    cfg: PortfolioConfig,
    previous_weights: pd.Series | None,
) -> pd.Series | None:
    if signal_scores.empty:
        return pd.Series(dtype=float, name="weight")

    max_name_weight = max(float(cfg.max_name_weight), 0.0)
    gross_target = max(float(cfg.gross_target), 0.0)
    if max_name_weight <= 0 or gross_target < 0:
        return pd.Series(dtype=float, name="weight")

    candidates = signal_scores.copy()
    if cfg.qp_max_names > 0 and len(candidates) > cfg.qp_max_names:
        candidates = candidates.loc[candidates.abs().nlargest(int(cfg.qp_max_names)).index]
    if candidates.empty:
        return pd.Series(dtype=float, name="weight")

    mu_series = _build_rank_based_mu(
        scores=candidates,
        clip_value=float(cfg.qp_mu_clip),
    )
    if mu_series.empty:
        return pd.Series(dtype=float, name="weight")

    n_assets = len(mu_series)
    cap_feasible_net = min(gross_target, n_assets * max_name_weight)
    net_target = float(np.clip(cfg.net_target, -cap_feasible_net, cap_feasible_net))
    if gross_target < abs(net_target) - 1e-12:
        if gross_target <= 0:
            return pd.Series(dtype=float, name="weight")
        net_target = float(np.sign(net_target) * gross_target)

    cov = _estimate_covariance_matrix(
        train_frame=train_frame,
        tickers=mu_series.index,
        lookback=int(cfg.qp_cov_lookback),
        use_shrinkage=bool(cfg.qp_cov_shrinkage),
        ridge=float(cfg.qp_cov_ridge),
        return_col="next_period_return",
    )
    mu = mu_series.to_numpy(dtype=float)
    prev_w = (
        previous_weights.reindex(mu_series.index, fill_value=0.0).to_numpy(dtype=float)
        if previous_weights is not None
        else np.zeros(n_assets, dtype=float)
    )
    risk_aversion = max(float(cfg.qp_risk_aversion), 0.0)
    turnover_penalty = max(float(cfg.qp_turnover_penalty), 0.0)

    def _weights_from_x(x: np.ndarray) -> np.ndarray:
        return x[:n_assets] - x[n_assets:]

    def _objective(x: np.ndarray) -> float:
        w = _weights_from_x(x)
        risk_term = float(w @ cov @ w)
        turnover_term = float(np.square(w - prev_w).sum())
        signal_term = float(mu @ w)
        return -signal_term + risk_aversion * risk_term + turnover_penalty * turnover_term

    constraints: list[dict[str, object]] = [
        {
            "type": "eq",
            "fun": lambda x: float(np.sum(x[:n_assets]) - np.sum(x[n_assets:]) - net_target),
        }
    ]
    if gross_target >= 0:
        constraints.append(
            {
                "type": "ineq",
                "fun": lambda x: float(gross_target - np.sum(x[:n_assets] + x[n_assets:])),
            }
        )

    bounds = [(0.0, max_name_weight)] * (2 * n_assets)
    x0 = _build_qp_initial_guess(
        mu=mu,
        max_name_weight=max_name_weight,
        gross_target=gross_target,
        net_target=net_target,
        previous_weights=prev_w,
    )

    try:
        result = minimize(
            _objective,
            x0=x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={
                "maxiter": int(cfg.qp_solver_max_iter),
                "ftol": float(cfg.qp_solver_ftol),
                "disp": False,
            },
        )
    except Exception:
        return None

    if not result.success:
        return None

    w = _weights_from_x(np.asarray(result.x, dtype=float))
    w = np.clip(w, -max_name_weight, max_name_weight)

    gross = float(np.abs(w).sum())
    net = float(w.sum())
    if gross > gross_target + 1e-4:
        return None
    if abs(net - net_target) > 1e-4:
        return None

    out = pd.Series(w, index=mu_series.index, dtype=float, name="weight")
    out = out[out.abs() > 1e-12].sort_index()
    return out


def build_portfolio_weights(
    *,
    predictions: np.ndarray,
    probs: np.ndarray | None,
    classes_: np.ndarray | None,
    raw_scores: np.ndarray | None = None,
    sample_index: pd.Index,
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    cfg: PortfolioConfig,
    previous_weights: pd.Series | None = None,
) -> pd.Series:
    """Build ticker-level long/short weights from model outputs."""
    if len(predictions) != len(sample_index):
        raise ValueError("predictions and sample_index must have equal length.")

    if raw_scores is None:
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
        return _with_portfolio_attrs(pd.Series(dtype=float, name="weight"))

    method = str(cfg.weighting_method).strip().lower()
    if method == "signal_risk_qp":
        qp_signal = _zscore_clip(active, zmax=cfg.winsor_z)
        if cfg.sector_neutral:
            sector_labels = _infer_sector_labels(
                frame_slice=test_frame,
                sample_index=sample_index,
                sector_prefix=cfg.sector_prefix,
            )
            qp_signal = _neutralize_by_group(qp_signal, sector_labels)
        qp_signal = qp_signal.where(qp_signal.abs() > 1e-12, 0.0)
        qp_signal = qp_signal[qp_signal != 0]
        if qp_signal.empty:
            return _with_portfolio_attrs(pd.Series(dtype=float, name="weight"))

        qp_weights = _solve_signal_risk_qp_weights(
            signal_scores=qp_signal,
            train_frame=train_frame,
            cfg=cfg,
            previous_weights=previous_weights,
        )
        if qp_weights is not None:
            return _with_portfolio_attrs(qp_weights, qp_fallback=False)
        if not cfg.qp_fallback_to_heuristic:
            return _with_portfolio_attrs(pd.Series(dtype=float, name="weight"))
        qp_fallback = True
    elif method != "heuristic":
        raise ValueError(
            "Unsupported weighting_method. Use 'heuristic' or 'signal_risk_qp'."
        )
    else:
        qp_fallback = False

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
        return _with_portfolio_attrs(pd.Series(dtype=float, name="weight"), qp_fallback=qp_fallback)

    return _with_portfolio_attrs(
        _build_heuristic_weights_from_scores(zscores, cfg=cfg),
        qp_fallback=qp_fallback,
    )


def portfolio_exposure_diagnostics(
    *,
    weights: pd.Series,
    cfg: PortfolioConfig,
) -> dict[str, float | bool]:
    """Summarize target and realized exposure for a period."""
    target_gross = max(float(cfg.gross_target), 0.0)
    target_net = float(np.clip(cfg.net_target, -target_gross, target_gross))
    realized_gross = float(weights.abs().sum()) if not weights.empty else 0.0
    realized_net = float(weights.sum()) if not weights.empty else 0.0
    return {
        "target_gross": target_gross,
        "realized_gross": realized_gross,
        "target_net": target_net,
        "realized_net": realized_net,
        "unallocated_exposure": max(0.0, target_gross - realized_gross),
        "qp_fallback": bool(weights.attrs.get("qp_fallback", False)),
    }


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
