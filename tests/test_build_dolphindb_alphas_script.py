from __future__ import annotations

import argparse
import builtins
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd
import pytest

from moneytree.factors.external import external_alpha_columns
from scripts import build_dolphindb_alphas


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-04", "2021-01-05"]),
            "ticker": ["000001.SZ", "000002.SZ"],
            "open_adj": [10.0, 20.0],
            "high_adj": [10.5, 20.5],
            "low_adj": [9.5, 19.5],
            "close_adj": [10.2, 20.2],
            "vwap_adj": [10.1, 20.1],
            "volume": [1000.0, 2000.0],
            "circ_mv": [10000.0, 20000.0],
            "industry": ["bank", "tech"],
            "benchmark_open": [4000.0, 4010.0],
            "benchmark_close": [4005.0, 4015.0],
            "next_period_return": [0.01, -0.01],
            "benchmark_next_period_return": [0.0, 0.0],
            "benchmark_cum_ret": [1.0, 1.001],
        }
    )


class FakeSession:
    def __init__(self, *, missing_column: bool = False) -> None:
        self.missing_column = missing_column
        self.uploaded: dict[str, pd.DataFrame] = {}
        self.connected: tuple[Any, ...] | None = None
        self.scripts: list[str] = []

    def connect(self, host: str, port: int, user: str, password: str) -> None:
        self.connected = (host, port, user, password)

    def upload(self, values: dict[str, pd.DataFrame]) -> None:
        self.uploaded.update(values)

    def run(self, script: str) -> Any:
        self.scripts.append(script)
        if script == "version()":
            return "test-ddb"
        if "calcMoneyTreeAlpha101" in script:
            return self._alpha_result("alpha101")
        return None

    def _alpha_result(self, family: str) -> pd.DataFrame:
        raw = self.uploaded["rawData"]
        values = {
            "tradetime": raw["tradetime"],
            "securityid": raw["securityid"],
        }
        columns = external_alpha_columns(family)
        if self.missing_column:
            columns = columns[:-1]
        for idx, column in enumerate(columns):
            values[column] = float(idx + 1)
        return pd.DataFrame(values)


class FakeDolphinDB(ModuleType):
    def __init__(self, session: FakeSession) -> None:
        super().__init__("dolphindb")
        self.session = session

    def Session(self) -> FakeSession:
        return self.session


def _args(input_path: Path, output_path: Path, **overrides: Any) -> argparse.Namespace:
    values = {
        "input": str(input_path),
        "output": str(output_path),
        "manifest_output": None,
        "host": "127.0.0.1",
        "port": 8848,
        "user": "admin",
        "password": "supersecret",
        "family": None,
        "alpha101": True,
        "alpha191": False,
        "raw_price_fields": False,
        "alpha101_function": "calcMoneyTreeAlpha101",
        "alpha191_function": "calcMoneyTreeAlpha191",
        "wq101_module_version": "wq-test",
        "gtja191_module_version": "gtja-test",
        "moneytree_alpha_module_version": "wrapper-test",
        "compression": "snappy",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_dolphindb_generation_script_smoke_with_mocked_session(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    _panel().to_parquet(input_path)
    session = FakeSession()

    result = build_dolphindb_alphas.run_generation(
        _args(input_path, output_path),
        ddb_module=FakeDolphinDB(session),
    )

    manifest_path = output_path.with_suffix(output_path.suffix + ".factor_manifest.json")
    out = pd.read_parquet(output_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result.rows == 2
    assert result.alpha_columns == 101
    assert output_path.exists()
    assert manifest_path.exists()
    assert "alpha101_001" in out.columns
    assert "alpha101_101" in out.columns
    assert session.connected == ("127.0.0.1", 8848, "admin", "supersecret")
    assert "supersecret" not in json.dumps(manifest, sort_keys=True)
    assert manifest["output_data"]["path"] == str(output_path)
    assert manifest["module_versions"]["wq101alpha"] == "wq-test"


def test_dolphindb_generation_script_removes_temp_files_on_validation_failure(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    _panel().to_parquet(input_path)
    session = FakeSession(missing_column=True)

    with pytest.raises(Exception, match="missing columns"):
        build_dolphindb_alphas.run_generation(
            _args(input_path, output_path),
            ddb_module=FakeDolphinDB(session),
        )

    manifest_path = output_path.with_suffix(output_path.suffix + ".factor_manifest.json")
    leftovers = list(tmp_path.glob(".output.parquet.*.tmp"))
    assert not output_path.exists()
    assert not manifest_path.exists()
    assert leftovers == []


def test_load_dolphindb_client_reports_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any):
        if name == "dolphindb":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="uv pip install dolphindb"):
        build_dolphindb_alphas.load_dolphindb_client()
