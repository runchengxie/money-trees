from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from moneytree.model import FeatureSelectionResult


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


@dataclass
class ModelPreparationResult:
    selected_features: list[str]
    model_params: dict[str, Any]
    tuning_best_value: float
    selection_history: pd.DataFrame | None = None


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

    def prepare_training(
        self,
        *,
        train_x: pd.DataFrame,
        train_y: np.ndarray,
        train_returns: np.ndarray,
        valid_x: pd.DataFrame,
        valid_returns: np.ndarray,
        feature_selection: str,
        n_trials: int,
        random_state: int,
        cost_bps: float,
        tuning_cv_folds: int,
        min_features: int,
        max_steps: int,
        base_params: dict[str, Any] | None = None,
    ) -> ModelPreparationResult:
        params, best_value = self.tune(
            train_x=train_x,
            train_y=train_y,
            train_returns=train_returns,
            valid_x=valid_x,
            valid_returns=valid_returns,
            n_trials=n_trials,
            random_state=random_state,
            cost_bps=cost_bps,
            tuning_cv_folds=tuning_cv_folds,
            base_params=base_params,
        )
        selection = self.select_features(
            method=feature_selection,
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
        return ModelPreparationResult(
            selected_features=list(selection.selected_features),
            model_params=params,
            tuning_best_value=best_value,
            selection_history=selection.history,
        )
