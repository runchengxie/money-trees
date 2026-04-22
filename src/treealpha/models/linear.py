from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet, Lasso, Ridge

from strategy.model import FeatureSelectionResult

from .base import BaseModelAdapter, ModelCapabilities, ModelOutputs


class _BaseLinearAdapter(BaseModelAdapter):
    training_target_column = "rel_return"
    capabilities = ModelCapabilities(
        supports_tuning=False,
        supported_feature_selection=("none",),
        supports_probability_scores=False,
    )
    estimator_cls: type
    _default_params: dict[str, Any]

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
        model_params = self.default_params()
        if params is not None:
            model_params.update(params)
        if "random_state" in self.estimator_cls().get_params():
            model_params.setdefault("random_state", random_state)
        model = self.estimator_cls(**model_params)
        model.fit(train_x, train_y)
        return model

    def predict_outputs(self, *, model, features: pd.DataFrame) -> ModelOutputs:
        scores = np.asarray(model.predict(features), dtype=float)
        discrete = np.sign(scores).astype(int)
        return ModelOutputs(scores=scores, predictions=discrete)

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


class RidgeAdapter(_BaseLinearAdapter):
    model_id = "ridge"
    estimator_cls = Ridge
    _default_params = {"alpha": 1.0}


class LassoAdapter(_BaseLinearAdapter):
    model_id = "lasso"
    estimator_cls = Lasso
    _default_params = {"alpha": 0.001, "max_iter": 5000}


class ElasticNetAdapter(_BaseLinearAdapter):
    model_id = "elasticnet"
    estimator_cls = ElasticNet
    _default_params = {"alpha": 0.001, "l1_ratio": 0.5, "max_iter": 5000}
