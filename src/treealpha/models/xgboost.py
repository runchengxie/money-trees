from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategy.portfolio import build_signal_scores

from .base import BaseModelAdapter, ModelCapabilities, ModelOutputs


@dataclass
class _XGBoostBundle:
    model: Any
    classes_: np.ndarray


class XGBoostAdapter(BaseModelAdapter):
    model_id = "xgboost"
    training_target_column = "rel_performance"
    capabilities = ModelCapabilities(
        supports_tuning=False,
        supported_feature_selection=("none",),
        supports_probability_scores=True,
    )

    def _load_estimator(self):
        try:
            from xgboost import XGBClassifier
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Model 'xgboost' requires the optional xgboost dependency. "
                "Install it with the project's xgboost extra."
            ) from exc
        return XGBClassifier

    def default_params(self) -> dict[str, Any]:
        return {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "objective": "multi:softprob",
            "eval_metric": "mlogloss",
        }

    def fit(
        self,
        *,
        train_x: pd.DataFrame,
        train_y: np.ndarray,
        params: dict[str, Any] | None = None,
        random_state: int = 123,
    ):
        estimator_cls = self._load_estimator()
        model_params = self.default_params()
        if params is not None:
            model_params.update(params)
        model_params.setdefault("random_state", random_state)
        classes_ = np.array(sorted(pd.unique(train_y)))
        label_map = {label: idx for idx, label in enumerate(classes_)}
        encoded = np.asarray([label_map[val] for val in train_y], dtype=int)
        model = estimator_cls(**model_params)
        model.fit(train_x, encoded)
        return _XGBoostBundle(model=model, classes_=classes_)

    def predict_outputs(self, *, model: _XGBoostBundle, features: pd.DataFrame) -> ModelOutputs:
        encoded_predictions = np.asarray(model.model.predict(features), dtype=int)
        predictions = model.classes_[encoded_predictions]
        probabilities = model.model.predict_proba(features)
        scores = build_signal_scores(
            predictions=predictions,
            probs=probabilities,
            classes_=model.classes_,
            use_prob_signal=True,
        )
        return ModelOutputs(
            scores=np.asarray(scores, dtype=float),
            predictions=np.asarray(predictions),
            probabilities=probabilities,
            classes_=model.classes_,
        )
