from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategy.model import FeatureSelectionResult


@dataclass(frozen=True)
class ModelCapabilities:
    supports_tuning: bool
    supported_feature_selection: tuple[str, ...]
    supports_probability_scores: bool


@dataclass
class ModelOutputs:
    scores: np.ndarray
    predictions: np.ndarray | None = None
    probabilities: np.ndarray | None = None
    classes_: np.ndarray | None = None


class BaseModelAdapter(ABC):
    model_id: str
    training_target_column: str
    capabilities: ModelCapabilities

    @abstractmethod
    def default_params(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fit(
        self,
        *,
        train_x: pd.DataFrame,
        train_y: np.ndarray,
        params: dict[str, Any] | None = None,
        random_state: int = 123,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def predict_outputs(
        self,
        *,
        model: Any,
        features: pd.DataFrame,
    ) -> ModelOutputs:
        raise NotImplementedError

    def validate_configuration(
        self,
        *,
        feature_selection: str,
        n_trials: int,
    ) -> None:
        if feature_selection not in self.capabilities.supported_feature_selection:
            supported = ", ".join(self.capabilities.supported_feature_selection)
            raise ValueError(
                f"Model '{self.model_id}' does not support feature_selection="
                f"'{feature_selection}'. Supported values: {supported}."
            )
        if n_trials > 0 and not self.capabilities.supports_tuning:
            raise ValueError(
                f"Model '{self.model_id}' does not support hyperparameter tuning. "
                "Set n_trials=0 for this adapter."
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
            return dict(base_params or self.default_params()), float("nan")
        raise ValueError(f"Model '{self.model_id}' does not implement tuning.")

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
        raise ValueError(
            f"Model '{self.model_id}' does not implement feature selection method '{method}'."
        )
