from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
)

from moneytree.model import (
    FeatureSelectionResult,
    select_positive_importance_features,
)
from moneytree.portfolio import build_signal_scores

from .base import BaseModelAdapter, ModelCapabilities, ModelOutputs


class _SklearnTreeClassifierAdapter(BaseModelAdapter):
    training_target_column = "rel_performance"
    capabilities = ModelCapabilities(
        supports_tuning=False,
        supported_feature_selection=("none", "importance"),
        supports_probability_scores=True,
    )
    estimator_cls: type | None = None
    _default_params: dict[str, Any] = {}

    def default_params(self) -> dict[str, Any]:
        return dict(self._default_params)

    def fit(
        self,
        *,
        train_x: pd.DataFrame,
        train_y: np.ndarray,
        params: dict[str, Any] | None = None,
        random_state: int = 123,
    ):
        if self.estimator_cls is None:
            raise RuntimeError(f"Model '{self.model_id}' is not fully configured.")
        model_params = self.default_params()
        if params is not None:
            model_params.update(params)
        model_params.setdefault("random_state", random_state)
        model = self.estimator_cls(**model_params)
        model.fit(train_x, np.asarray(train_y))
        return model

    def predict_outputs(self, *, model, features: pd.DataFrame) -> ModelOutputs:
        predictions = np.asarray(model.predict(features))
        probabilities = model.predict_proba(features)
        classes_ = getattr(model, "classes_", None)
        scores = build_signal_scores(
            predictions=predictions,
            probs=probabilities,
            classes_=classes_,
            use_prob_signal=True,
        )
        return ModelOutputs(
            scores=np.asarray(scores, dtype=float),
            predictions=predictions,
            probabilities=probabilities,
            classes_=classes_,
        )

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
                selected_features=select_positive_importance_features(
                    model, list(train_x.columns)
                )
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


class ExtraTreesAdapter(_SklearnTreeClassifierAdapter):
    model_id = "extra_trees"
    estimator_cls = ExtraTreesClassifier
    _default_params: dict[str, Any] = {
        "n_estimators": 300,
        "max_depth": 12,
        "min_samples_leaf": 4,
        "max_features": "sqrt",
    }


class GradientBoostingAdapter(_SklearnTreeClassifierAdapter):
    model_id = "gradient_boosting"
    estimator_cls = GradientBoostingClassifier
    _default_params: dict[str, Any] = {
        "n_estimators": 300,
        "learning_rate": 0.05,
        "max_depth": 3,
        "min_samples_leaf": 50,
        "subsample": 0.8,
    }


class HistGradientBoostingAdapter(_SklearnTreeClassifierAdapter):
    model_id = "hist_gradient_boosting"
    estimator_cls = HistGradientBoostingClassifier
    capabilities = ModelCapabilities(
        supports_tuning=False,
        supported_feature_selection=("none",),
        supports_probability_scores=True,
    )
    _default_params: dict[str, Any] = {
        "max_iter": 300,
        "learning_rate": 0.05,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 50,
        "l2_regularization": 0.0,
    }
