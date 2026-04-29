from __future__ import annotations

import tomllib
from pathlib import Path

import moneytree
from moneytree.metadata import runtime_metadata


def _pyproject() -> dict:
    root = Path(__file__).resolve().parents[1]
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))


def test_distribution_identity_keeps_moneytree_import() -> None:
    project = _pyproject()["project"]

    assert project["name"] == "money-trees"
    assert moneytree.__name__ == "moneytree"


def test_console_script_aliases_point_to_expected_entrypoints() -> None:
    scripts = _pyproject()["project"]["scripts"]

    assert scripts["moneytree"] == "moneytree.cli.backtest:main"
    assert scripts["moneytrees"] == "moneytree.cli.backtest:main"
    assert scripts["moneytree-tushare"] == "moneytree.cli.tushare:main"
    assert scripts["moneytrees-tushare"] == "moneytree.cli.tushare:main"
    assert scripts["moneytree-data-status"] == "moneytree.cli.data_status:main"
    assert scripts["moneytrees-data-status"] == "moneytree.cli.data_status:main"
    assert scripts["moneytree-data-snapshot"] == "moneytree.cli.data_snapshot:main"
    assert scripts["moneytrees-data-snapshot"] == "moneytree.cli.data_snapshot:main"
    assert scripts["moneytree-dolphindb-alphas"] == "moneytree.cli.dolphindb_alphas:main"
    assert scripts["moneytrees-dolphindb-alphas"] == "moneytree.cli.dolphindb_alphas:main"
    assert scripts["moneytree-factor-store"] == "moneytree.cli.factor_store:main"
    assert scripts["moneytrees-factor-store"] == "moneytree.cli.factor_store:main"
    assert scripts["moneytree-parquet-rewrite"] == "moneytree.cli.parquet_rewrite:main"
    assert scripts["moneytrees-parquet-rewrite"] == "moneytree.cli.parquet_rewrite:main"


def test_optional_dependency_groups_expose_research_intent() -> None:
    optional = _pyproject()["project"]["optional-dependencies"]
    dependencies = _pyproject()["project"]["dependencies"]

    assert "optuna" not in dependencies
    assert optional["external-alphas"] == ["dolphindb"]
    assert optional["tuning"] == ["optuna"]
    assert set(optional["research"]) == {"tushare", "xgboost", "dolphindb", "optuna"}


def test_runtime_metadata_tracks_money_trees_distribution() -> None:
    packages = runtime_metadata()["packages"]

    assert "money-trees" in packages
    assert "money-tree" not in packages
