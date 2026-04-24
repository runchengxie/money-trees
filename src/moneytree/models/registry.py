from __future__ import annotations

from moneytree.models.base import BaseModelAdapter
from moneytree.models.linear import ElasticNetAdapter, LassoAdapter, RidgeAdapter
from moneytree.models.random_forest import RandomForestAdapter
from moneytree.models.xgboost import XGBoostAdapter, XGBoostRegressorAdapter


_MODEL_REGISTRY: dict[str, BaseModelAdapter] = {
    "random_forest": RandomForestAdapter(),
    "ridge": RidgeAdapter(),
    "lasso": LassoAdapter(),
    "elasticnet": ElasticNetAdapter(),
    "xgboost": XGBoostAdapter(),
    "xgboost_regressor": XGBoostRegressorAdapter(),
}


def register_model_adapter(adapter: BaseModelAdapter) -> None:
    _MODEL_REGISTRY[adapter.model_id] = adapter


def get_model_adapter(model_id: str) -> BaseModelAdapter:
    try:
        return _MODEL_REGISTRY[model_id]
    except KeyError as exc:
        available = ", ".join(sorted(_MODEL_REGISTRY))
        raise KeyError(f"Unknown model adapter '{model_id}'. Available: {available}.") from exc


def list_model_adapters() -> list[str]:
    return sorted(_MODEL_REGISTRY)
