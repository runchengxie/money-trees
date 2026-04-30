from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

DEFAULT_RF_PARAMS: dict[str, Any] = {
    "n_estimators": 100,
    "max_depth": 35,
    "min_samples_leaf": 50,
    "max_features": "sqrt",
}


@dataclass
class FeatureSelectionResult:
    selected_features: list[str]
    history: pd.DataFrame | None = None


def _load_optuna():
    try:
        import optuna
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Hyperparameter tuning requires the optional optuna dependency. "
            "Install it with `uv sync --dev --extra tuning` or "
            "`uv sync --dev --extra research`."
        ) from exc
    return optuna


def build_random_forest(
    params: dict[str, Any] | None = None,
    random_state: int = 123,
    n_jobs: int = -1,
) -> RandomForestClassifier:
    model_params = dict(DEFAULT_RF_PARAMS)
    if params is not None:
        model_params.update(params)
    model_params["random_state"] = random_state
    model_params["n_jobs"] = n_jobs
    return RandomForestClassifier(**model_params)


def signal_profit(
    predictions: np.ndarray,
    realized_returns: np.ndarray,
    cost_bps: float = 0.0,
    turnover: float | None = None,
) -> float:
    """
    Compute equal-weight long/short period return with transaction cost.

    This avoids the unstable denominator bug from using predictions.sum().
    """
    active_count = int(np.count_nonzero(predictions))
    if active_count == 0:
        return 0.0

    weights = predictions.astype(float) / active_count
    gross_return = float(np.dot(weights, realized_returns))
    if turnover is None:
        # If turnover is not provided, assume this period opens the current
        # equal-weight book from flat.
        turnover_value = float(0.5 * np.abs(weights).sum())
    else:
        turnover_value = max(float(turnover), 0.0)
    trading_cost = (cost_bps / 10000.0) * turnover_value
    return gross_return - trading_cost


def predictions_to_name_weights(
    predictions: np.ndarray,
    sample_index: pd.Index | None = None,
) -> pd.Series:
    """Convert raw predictions into equal-weight name-level positions."""
    if sample_index is None:
        index = pd.RangeIndex(start=0, stop=len(predictions))
    else:
        if len(sample_index) != len(predictions):
            raise ValueError("sample_index length must match predictions length.")
        index = sample_index

    signal = pd.Series(predictions, index=index, dtype=float)
    if isinstance(signal.index, pd.MultiIndex) and "ticker" in signal.index.names:
        signal = signal.groupby(level="ticker", sort=False).last()

    active = signal[signal != 0]
    if active.empty:
        return pd.Series(dtype=float, name="weight")

    weights = active / len(active)
    weights.name = "weight"
    return weights


def count_active_names(
    predictions: np.ndarray,
    sample_index: pd.Index | None = None,
) -> int:
    """Count unique active names (ticker-level for MultiIndex inputs)."""
    weights = predictions_to_name_weights(predictions, sample_index=sample_index)
    return int(len(weights))


def estimate_turnover(
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


def profit_with_estimated_turnover(
    predictions: np.ndarray,
    realized_returns: np.ndarray,
    cost_bps: float = 0.0,
    sample_index: pd.Index | None = None,
    previous_weights: pd.Series | None = None,
) -> tuple[float, pd.Series, float]:
    """Compute period profit using turnover estimated from name-level weights."""
    current_weights = predictions_to_name_weights(predictions, sample_index=sample_index)
    turnover = estimate_turnover(current_weights, previous_weights=previous_weights)
    profit = signal_profit(
        predictions=predictions,
        realized_returns=realized_returns,
        cost_bps=cost_bps,
        turnover=turnover,
    )
    return float(profit), current_weights, float(turnover)


def score_predictions_over_time(
    predictions: np.ndarray,
    realized_returns: np.ndarray,
    sample_index: pd.Index,
    cost_bps: float = 0.0,
) -> float:
    """
    Score predictions by averaging period profits across dates.

    If the index is not date-aware, it falls back to a single-period score.
    """
    if len(predictions) == 0:
        return 0.0
    if len(predictions) != len(realized_returns) or len(predictions) != len(sample_index):
        raise ValueError("predictions, realized_returns, and sample_index must have equal length.")

    if not (isinstance(sample_index, pd.MultiIndex) and "date" in sample_index.names):
        score, _, _ = profit_with_estimated_turnover(
            predictions=predictions,
            realized_returns=realized_returns,
            cost_bps=cost_bps,
            sample_index=sample_index,
            previous_weights=None,
        )
        return float(score)

    date_values = pd.Index(sample_index.get_level_values("date"))
    unique_dates = pd.Index(date_values.unique()).sort_values()
    period_scores: list[float] = []
    previous_weights: pd.Series | None = None

    for dt in unique_dates:
        mask = np.asarray(date_values == dt)
        if not np.any(mask):
            continue
        period_score, previous_weights, _ = profit_with_estimated_turnover(
            predictions=predictions[mask],
            realized_returns=realized_returns[mask],
            cost_bps=cost_bps,
            sample_index=sample_index[mask],
            previous_weights=previous_weights,
        )
        period_scores.append(float(period_score))

    if not period_scores:
        return 0.0
    return float(np.mean(period_scores))


def _build_time_series_cv_splits(
    sample_index: pd.Index,
    n_folds: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    if n_folds <= 1:
        return []

    if isinstance(sample_index, pd.MultiIndex) and "date" in sample_index.names:
        date_values = pd.Index(sample_index.get_level_values("date"))
        unique_dates = pd.Index(date_values.unique()).sort_values()
        if len(unique_dates) < n_folds + 1:
            raise ValueError(
                f"Not enough unique dates ({len(unique_dates)}) for tuning_cv_folds={n_folds}."
            )

        date_blocks = [blk for blk in np.array_split(unique_dates.to_numpy(), n_folds + 1) if len(blk)]
        if len(date_blocks) < 2:
            raise ValueError("Unable to build non-empty time-series CV date blocks.")

        splits: list[tuple[np.ndarray, np.ndarray]] = []
        for i in range(1, len(date_blocks)):
            train_dates = np.concatenate(date_blocks[:i])
            valid_dates = date_blocks[i]
            train_idx = np.flatnonzero(date_values.isin(train_dates))
            valid_idx = np.flatnonzero(date_values.isin(valid_dates))
            if len(train_idx) == 0 or len(valid_idx) == 0:
                continue
            splits.append((train_idx, valid_idx))

        if not splits:
            raise ValueError("No valid time-series CV split could be constructed.")
        return splits

    n_samples = len(sample_index)
    if n_samples < n_folds + 1:
        raise ValueError(f"Not enough samples ({n_samples}) for tuning_cv_folds={n_folds}.")

    sample_blocks = [blk for blk in np.array_split(np.arange(n_samples), n_folds + 1) if len(blk)]
    if len(sample_blocks) < 2:
        raise ValueError("Unable to build non-empty CV sample blocks.")

    splits: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(1, len(sample_blocks)):
        train_idx = np.concatenate(sample_blocks[:i])
        valid_idx = sample_blocks[i]
        if len(train_idx) == 0 or len(valid_idx) == 0:
            continue
        splits.append((train_idx, valid_idx))
    if not splits:
        raise ValueError("No valid CV split could be constructed.")
    return splits


def _suggest_random_forest_params(
    trial: Any,
    *,
    search_space: str,
) -> dict[str, Any]:
    if search_space == "notebook_compat":
        return {
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 50, 1200, step=50),
            "max_depth": trial.suggest_int("max_depth", 5, 40, step=5),
            "n_estimators": trial.suggest_int("n_estimators", 5, 50, step=5),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2"]),
        }
    return {
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 50, 1200, step=50),
        "max_depth": trial.suggest_int("max_depth", 5, 40, step=5),
        "n_estimators": trial.suggest_int("n_estimators", 10, 120, step=10),
        "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2"]),
    }


def tune_random_forest(
    train_x: pd.DataFrame,
    train_y: np.ndarray,
    train_returns: np.ndarray,
    valid_x: pd.DataFrame,
    valid_returns: np.ndarray,
    n_trials: int = 50,
    random_state: int = 123,
    cost_bps: float = 0.0,
    tuning_cv_folds: int = 1,
    search_space: str = "default",
) -> tuple[dict[str, Any], float]:
    """Tune RF hyperparameters with trading profit as objective."""

    optuna = _load_optuna()
    sampler = optuna.samplers.TPESampler(seed=random_state)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    cv_splits = _build_time_series_cv_splits(train_x.index, tuning_cv_folds)

    def objective(trial: Any) -> float:
        params = _suggest_random_forest_params(trial, search_space=search_space)
        if tuning_cv_folds > 1:
            fold_scores: list[float] = []
            for fold_id, (train_idx, valid_idx) in enumerate(cv_splits):
                model = build_random_forest(
                    params=params,
                    random_state=random_state + fold_id,
                    n_jobs=1,
                )
                train_fold_x = train_x.iloc[train_idx]
                valid_fold_x = train_x.iloc[valid_idx]
                train_fold_y = train_y[train_idx]
                valid_fold_returns = train_returns[valid_idx]
                model.fit(train_fold_x, train_fold_y)
                preds = model.predict(valid_fold_x)
                fold_score = score_predictions_over_time(
                    predictions=preds,
                    realized_returns=valid_fold_returns,
                    sample_index=valid_fold_x.index,
                    cost_bps=cost_bps,
                )
                fold_scores.append(float(fold_score))
            return float(np.mean(fold_scores)) if fold_scores else 0.0

        model = build_random_forest(params=params, random_state=random_state, n_jobs=1)
        model.fit(train_x, train_y)
        preds = model.predict(valid_x)
        return score_predictions_over_time(
            predictions=preds,
            realized_returns=valid_returns,
            sample_index=valid_x.index,
            cost_bps=cost_bps,
        )

    study.optimize(objective, n_trials=n_trials, n_jobs=1)
    return study.best_params, float(study.best_value)


def fit_random_forest(
    train_x: pd.DataFrame,
    train_y: np.ndarray,
    params: dict[str, Any] | None = None,
    random_state: int = 123,
) -> RandomForestClassifier:
    model = build_random_forest(params=params, random_state=random_state)
    model.fit(train_x, train_y)
    return model


def feature_importance_frame(
    model: RandomForestClassifier,
    columns: list[str],
) -> pd.DataFrame:
    fi = pd.DataFrame({"cols": columns, "feat_imp": model.feature_importances_})
    return fi.sort_values("feat_imp", ascending=False).reset_index(drop=True)


def select_positive_importance_features(
    model: RandomForestClassifier,
    columns: list[str],
) -> list[str]:
    fi = feature_importance_frame(model, columns)
    selected = fi.loc[fi["feat_imp"] > 0.0, "cols"].tolist()
    if selected:
        return selected
    # Fallback to top feature if RF assigns all-zero importances.
    return fi.head(1)["cols"].tolist()


def permutation_profit_importance(
    model: RandomForestClassifier,
    valid_x: pd.DataFrame,
    valid_returns: np.ndarray,
    random_state: int = 123,
    cost_bps: float = 0.0,
) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    scores: list[dict[str, float | str]] = []

    for col in valid_x.columns:
        shuffled = valid_x.copy()
        shuffled[col] = rng.permutation(shuffled[col].to_numpy())
        preds = model.predict(shuffled)
        score, _, _ = profit_with_estimated_turnover(
            predictions=preds,
            realized_returns=valid_returns,
            cost_bps=cost_bps,
            sample_index=valid_x.index,
            previous_weights=None,
        )
        scores.append({"cols": col, "pi_imp": float(score)})

    return pd.DataFrame(scores).sort_values("pi_imp", ascending=True).reset_index(drop=True)


def sequential_feature_selection(
    train_x: pd.DataFrame,
    train_y: np.ndarray,
    valid_x: pd.DataFrame,
    valid_returns: np.ndarray,
    params: dict[str, Any],
    random_state: int = 123,
    min_features: int = 2,
    max_steps: int | None = None,
    cost_bps: float = 0.0,
) -> FeatureSelectionResult:
    """
    Drop one feature per step based on permutation profit importance.

    Chooses the best iteration by argmax(score), avoiding any hard-coded index.
    """
    current_cols = list(train_x.columns)
    if len(current_cols) <= min_features:
        return FeatureSelectionResult(selected_features=current_cols)

    history: list[dict[str, Any]] = []
    best_cols = current_cols.copy()
    best_score = -np.inf
    step = 0

    while len(current_cols) > min_features:
        if max_steps is not None and step >= max_steps:
            break

        model = fit_random_forest(
            train_x=train_x[current_cols],
            train_y=train_y,
            params=params,
            random_state=random_state,
        )
        preds = model.predict(valid_x[current_cols])
        score, _, _ = profit_with_estimated_turnover(
            predictions=preds,
            realized_returns=valid_returns,
            cost_bps=cost_bps,
            sample_index=valid_x.index,
            previous_weights=None,
        )

        if score > best_score:
            best_score = score
            best_cols = current_cols.copy()

        pi = permutation_profit_importance(
            model=model,
            valid_x=valid_x[current_cols],
            valid_returns=valid_returns,
            random_state=random_state + step,
            cost_bps=cost_bps,
        )
        drop_col = str(pi.iloc[-1]["cols"])
        history.append(
            {
                "step": step,
                "n_features": len(current_cols),
                "score": float(score),
                "dropped_feature": drop_col,
            }
        )
        current_cols.remove(drop_col)
        step += 1

    history_frame = pd.DataFrame(history)
    return FeatureSelectionResult(selected_features=best_cols, history=history_frame)


def notebook_compat_feature_selection(
    train_x: pd.DataFrame,
    train_y: np.ndarray,
    train_returns: np.ndarray,
    valid_x: pd.DataFrame,
    valid_returns: np.ndarray,
    base_params: dict[str, Any] | None = None,
    n_trials: int = 50,
    random_state: int = 123,
    cost_bps: float = 0.0,
    tuning_cv_folds: int = 1,
    min_features: int = 2,
    max_steps: int | None = None,
) -> tuple[list[str], dict[str, Any], float, pd.DataFrame | None]:
    """
    Reproduce the notebook RF pipeline:
    positive importance filter -> tune -> sequential permutation elimination -> retune.
    """
    initial_params = dict(DEFAULT_RF_PARAMS)
    if base_params:
        initial_params.update(base_params)

    initial_model = fit_random_forest(
        train_x=train_x,
        train_y=train_y,
        params=initial_params,
        random_state=random_state,
    )
    selected_by_importance = select_positive_importance_features(initial_model, list(train_x.columns))
    if len(selected_by_importance) < min_features:
        ranked = feature_importance_frame(initial_model, list(train_x.columns))
        selected_by_importance = ranked.head(min_features)["cols"].tolist()
    train_importance = train_x[selected_by_importance]
    valid_importance = valid_x[selected_by_importance]

    tuned_params = dict(initial_params)
    tuned_best_value = float("nan")
    if n_trials > 0:
        tuned_params, tuned_best_value = tune_random_forest(
            train_x=train_importance,
            train_y=train_y,
            train_returns=train_returns,
            valid_x=valid_importance,
            valid_returns=valid_returns,
            n_trials=n_trials,
            random_state=random_state,
            cost_bps=cost_bps,
            tuning_cv_folds=tuning_cv_folds,
            search_space="notebook_compat",
        )
        if base_params:
            merged_tuned = dict(base_params)
            merged_tuned.update(tuned_params)
            tuned_params = merged_tuned

    sequential = sequential_feature_selection(
        train_x=train_importance,
        train_y=train_y,
        valid_x=valid_importance,
        valid_returns=valid_returns,
        params=tuned_params,
        random_state=random_state,
        min_features=min_features,
        max_steps=max_steps,
        cost_bps=cost_bps,
    )
    final_features = list(sequential.selected_features)

    final_params = dict(tuned_params)
    final_best_value = tuned_best_value
    if n_trials > 0:
        final_params, final_best_value = tune_random_forest(
            train_x=train_importance[final_features],
            train_y=train_y,
            train_returns=train_returns,
            valid_x=valid_importance[final_features],
            valid_returns=valid_returns,
            n_trials=n_trials,
            random_state=random_state + 1,
            cost_bps=cost_bps,
            tuning_cv_folds=tuning_cv_folds,
            search_space="notebook_compat",
        )
        if base_params:
            merged_final = dict(base_params)
            merged_final.update(final_params)
            final_params = merged_final

    return final_features, final_params, float(final_best_value), sequential.history
