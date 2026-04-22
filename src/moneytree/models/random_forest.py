from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from moneytree.model import (
    DEFAULT_RF_PARAMS,
    FeatureSelectionResult,
    fit_random_forest,
    select_positive_importance_features,
    sequential_feature_selection,
    tune_random_forest,
)
from moneytree.portfolio import build_signal_scores

from .base import BaseModelAdapter, ModelCapabilities, ModelOutputs


class RandomForestAdapter(BaseModelAdapter):
    model_id = "random_forest"
    training_target_column = "rel_performance"
    capabilities = ModelCapabilities(
        supports_tuning=True,
        supported_feature_selection=("none", "importance", "sequential"),
        supports_probability_scores=True,
    )

    def default_params(self) -> dict[str, Any]:
        return dict(DEFAULT_RF_PARAMS)

    def fit(
        self,
        *,
        train_x: pd.DataFrame,
        train_y: np.ndarray,
        params: dict[str, Any] | None = None,
        random_state: int = 123,
    ):
        model_params = self.default_params()
        if params is not None:
            model_params.update(params)
        return fit_random_forest(
            train_x=train_x,
            train_y=train_y,
            params=model_params,
            random_state=random_state,
        )

    def predict_outputs(self, *, model, features: pd.DataFrame) -> ModelOutputs:
        predictions = model.predict(features)
        probabilities = model.predict_proba(features) if hasattr(model, "predict_proba") else None
        classes_ = getattr(model, "classes_", None)
        scores = build_signal_scores(
            predictions=predictions,
            probs=probabilities,
            classes_=classes_,
            use_prob_signal=True,
        )
        return ModelOutputs(
            scores=np.asarray(scores, dtype=float),
            predictions=np.asarray(predictions),
            probabilities=probabilities,
            classes_=classes_,
        )

    def tune(
        self,
        *,
        train_x: pd.DataFrame,
        train_y: np.ndarray,
        train_returns: np.ndarray,
        valid_x: pd.DataFrame,
        valid_returns: np.ndarray,
        n_trials: int,
        random_state: int,
        cost_bps: float,
        tuning_cv_folds: int,
        base_params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], float]:
        if n_trials <= 0:
            params = self.default_params()
            if base_params is not None:
                params.update(base_params)
            return params, float("nan")

        tuned_params, best_value = tune_random_forest(
            train_x=train_x,
            train_y=train_y,
            train_returns=train_returns,
            valid_x=valid_x,
            valid_returns=valid_returns,
            n_trials=n_trials,
            random_state=random_state,
            cost_bps=cost_bps,
            tuning_cv_folds=tuning_cv_folds,
        )
        if base_params:
            merged = dict(base_params)
            merged.update(tuned_params)
            tuned_params = merged
        return tuned_params, best_value

    def select_features(
        self,
        *,
        method: str,
        train_x: pd.DataFrame,
        train_y: np.ndarray,
        valid_x: pd.DataFrame,
        valid_returns: np.ndarray,
        params: dict[str, Any],
        random_state: int,
        min_features: int,
        max_steps: int,
        cost_bps: float,
    ) -> FeatureSelectionResult:
        if method == "none":
            return FeatureSelectionResult(selected_features=list(train_x.columns))
        if method == "importance":
            model = self.fit(
                train_x=train_x,
                train_y=train_y,
                params=params,
                random_state=random_state,
            )
            return FeatureSelectionResult(
                selected_features=select_positive_importance_features(model, list(train_x.columns))
            )
        if method == "sequential":
            return sequential_feature_selection(
                train_x=train_x,
                train_y=train_y,
                valid_x=valid_x,
                valid_returns=valid_returns,
                params=params,
                random_state=random_state,
                min_features=min_features,
                max_steps=max_steps,
                cost_bps=cost_bps,
            )
        return super().select_features(
            method=method,
            train_x=train_x,
            train_y=train_y,
            valid_x=valid_x,
            valid_returns=valid_returns,
            params=params,
            random_state=random_state,
            min_features=min_features,
            max_steps=max_steps,
            cost_bps=cost_bps,
        )
