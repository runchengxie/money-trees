from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import optuna
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


def tune_random_forest(
    train_x: pd.DataFrame,
    train_y: np.ndarray,
    valid_x: pd.DataFrame,
    valid_returns: np.ndarray,
    n_trials: int = 50,
    random_state: int = 123,
    cost_bps: float = 0.0,
) -> tuple[dict[str, Any], float]:
    """Tune RF hyperparameters with trading profit as objective."""

    sampler = optuna.samplers.TPESampler(seed=random_state)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    def objective(trial: optuna.trial.Trial) -> float:
        params = {
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 50, 1200, step=50),
            "max_depth": trial.suggest_int("max_depth", 5, 40, step=5),
            "n_estimators": trial.suggest_int("n_estimators", 10, 120, step=10),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2"]),
        }
        model = build_random_forest(params=params, random_state=random_state, n_jobs=1)
        model.fit(train_x, train_y)
        preds = model.predict(valid_x)
        score, _, _ = profit_with_estimated_turnover(
            predictions=preds,
            realized_returns=valid_returns,
            cost_bps=cost_bps,
            sample_index=valid_x.index,
            previous_weights=None,
        )
        return score

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
