from __future__ import annotations

import argparse
import builtins
import json
from pathlib import Path
import re
from types import ModuleType
from typing import Any

import pandas as pd
import pytest

from moneytree.factors.external import external_alpha_columns
from moneytree.cli import dolphindb_alphas
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
    def __init__(
        self,
        *,
        missing_column: bool = False,
        missing_modules: set[str] | None = None,
        missing_functions: set[str] | None = None,
        function_results: dict[str, str] | None = None,
    ) -> None:
        self.missing_column = missing_column
        self.missing_modules = missing_modules or set()
        self.missing_functions = missing_functions or set()
        self.function_results = function_results or {
            "calcMoneyTreeAlpha101": "alpha101",
            "calcMoneyTreeAlpha191": "alpha191",
        }
        self.uploaded: dict[str, pd.DataFrame] = {}
        self.connected: tuple[Any, ...] | None = None
        self.scripts: list[str] = []

    def connect(self, host: str, port: int, user: str, password: str) -> None:
        self.connected = (host, port, user, password)

    def upload(self, values: dict[str, pd.DataFrame]) -> None:
        self.uploaded.update(values)

    def run(self, script: str) -> Any:
        self.scripts.append(script)
        for module_name in self.missing_modules:
            if f"use {module_name}" in script:
                raise RuntimeError(f"Can't find module [{module_name}]")
        if script == "version()":
            return "test-ddb"
        if "defs(" in script:
            match = re.search(r'defs\("([^"]+)"\)', script)
            function_name = match.group(1) if match else ""
            short_name = function_name.rsplit("::", 1)[-1]
            available = (
                short_name in self.function_results
                and short_name not in self.missing_functions
            )
            return pd.DataFrame({"name": [function_name] if available else []})
        for function_name, family in self.function_results.items():
            if f"{function_name}(rawData" in script:
                if function_name in self.missing_functions:
                    raise RuntimeError(f"Unknown function [{function_name}]")
                return self._alpha_result(family)
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
        "factor_dtype": "float32",
        "compression": "snappy",
        "compression_level": None,
        "row_group_size": None,
        "factor_store_output": None,
        "no_wide_output": False,
        "chunk_trade_dates": 60,
        "progress": False,
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
    assert str(out["alpha101_001"].dtype) == "float32"
    assert session.connected == ("127.0.0.1", 8848, "admin", "supersecret")
    assert "supersecret" not in json.dumps(manifest, sort_keys=True)
    assert manifest["output_data"]["path"] == str(output_path)
    assert manifest["factor_dtype"] == "float32"
    assert manifest["module_versions"]["wq101alpha"] == "wq-test"


def test_dolphindb_generation_package_cli_smoke_with_mocked_session(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    _panel().to_parquet(input_path)
    session = FakeSession()

    result = dolphindb_alphas.run_generation(
        _args(input_path, output_path),
        ddb_module=FakeDolphinDB(session),
    )

    assert result.rows == 2
    assert result.alpha_columns == 101
    assert output_path.exists()
    assert output_path.with_suffix(output_path.suffix + ".factor_manifest.json").exists()


def test_dolphindb_alpha101_preflight_loads_required_modules(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    _panel().to_parquet(input_path)
    session = FakeSession()

    dolphindb_alphas.run_generation(
        _args(input_path, output_path),
        ddb_module=FakeDolphinDB(session),
    )

    assert "use wq101alpha\n1" in session.scripts
    assert "use prepare101\n1" in session.scripts
    assert "use moneytreeAlpha\n1" in session.scripts
    calc_index = next(
        idx
        for idx, script in enumerate(session.scripts)
        if "calcMoneyTreeAlpha101(rawData" in script
    )
    preflight_indexes = [
        session.scripts.index("use wq101alpha\n1"),
        session.scripts.index("use prepare101\n1"),
        session.scripts.index("use moneytreeAlpha\n1"),
    ]
    assert max(preflight_indexes) < calc_index


def test_dolphindb_alpha191_preflight_loads_required_modules(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    _panel().to_parquet(input_path)
    session = FakeSession()

    result = dolphindb_alphas.run_generation(
        _args(input_path, output_path, alpha101=False, alpha191=True),
        ddb_module=FakeDolphinDB(session),
    )

    assert result.alpha_columns == 191
    assert "use gtja191Alpha\n1" in session.scripts
    assert "use gtja191Prepare\n1" in session.scripts
    assert "use moneytreeAlpha\n1" in session.scripts
    calc_index = next(
        idx
        for idx, script in enumerate(session.scripts)
        if "calcMoneyTreeAlpha191(rawData" in script
    )
    preflight_indexes = [
        session.scripts.index("use gtja191Alpha\n1"),
        session.scripts.index("use gtja191Prepare\n1"),
        session.scripts.index("use moneytreeAlpha\n1"),
    ]
    assert max(preflight_indexes) < calc_index


def test_dolphindb_preflight_reports_missing_module(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    _panel().to_parquet(input_path)
    session = FakeSession(missing_modules={"prepare101"})

    with pytest.raises(RuntimeError) as exc_info:
        dolphindb_alphas.run_generation(
            _args(input_path, output_path),
            ddb_module=FakeDolphinDB(session),
        )

    message = str(exc_info.value)
    assert "prepare101" in message
    assert "prepare101.dos" in message
    assert "docker/dolphindb/modules/" in message
    assert "--wq101-module-version" in message
    assert session.uploaded == {}


def test_dolphindb_preflight_reports_missing_wrapper_function(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    _panel().to_parquet(input_path)
    session = FakeSession(missing_functions={"calcMoneyTreeAlpha101"})

    with pytest.raises(RuntimeError) as exc_info:
        dolphindb_alphas.run_generation(
            _args(input_path, output_path),
            ddb_module=FakeDolphinDB(session),
        )

    message = str(exc_info.value)
    assert "calcMoneyTreeAlpha101" in message
    assert "moneytreeAlpha.dos" in message
    assert session.uploaded == {}


def test_dolphindb_preflight_uses_custom_wrapper_function_names(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    _panel().to_parquet(input_path)
    session = FakeSession(
        function_results={
            "customAlpha101": "alpha101",
            "customAlpha191": "alpha191",
        }
    )

    result = dolphindb_alphas.run_generation(
        _args(
            input_path,
            output_path,
            alpha101_function="customAlpha101",
            alpha191_function="customAlpha191",
            alpha191=True,
        ),
        ddb_module=FakeDolphinDB(session),
    )

    script_text = "\n---\n".join(session.scripts)
    assert result.alpha_columns == 292
    assert 'defs("moneytreeAlpha::customAlpha101")' in script_text
    assert 'defs("moneytreeAlpha::customAlpha191")' in script_text
    assert "customAlpha101(rawData, startTime, endTime)" in session.scripts
    assert "customAlpha191(rawData, startTime, endTime)" in session.scripts


def test_dolphindb_generation_can_write_factor_store_only(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    store_dir = tmp_path / "store"
    _panel().to_parquet(input_path)
    session = FakeSession()

    result = dolphindb_alphas.run_generation(
        _args(
            input_path,
            tmp_path / "unused.parquet",
            output=None,
            factor_store_output=str(store_dir),
            no_wide_output=True,
            chunk_trade_dates=1,
        ),
        ddb_module=FakeDolphinDB(session),
    )

    manifest_path = store_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result.output_path is None
    assert result.manifest_path is None
    assert result.factor_store_manifest_path == manifest_path
    assert result.alpha_columns == 101
    assert "alpha101" in manifest["factor_families"]
    assert len(manifest["factor_families"]["alpha101"]["paths"]) == 2
    assert "supersecret" not in json.dumps(manifest, sort_keys=True)


def test_dolphindb_generation_can_write_wide_and_factor_store(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    store_dir = tmp_path / "store"
    _panel().to_parquet(input_path)

    result = dolphindb_alphas.run_generation(
        _args(input_path, output_path, factor_store_output=str(store_dir), chunk_trade_dates=1),
        ddb_module=FakeDolphinDB(FakeSession()),
    )

    assert result.output_path == output_path
    assert output_path.exists()
    assert result.factor_store_manifest_path == store_dir / "manifest.json"
    assert (store_dir / "manifest.json").exists()


def test_dolphindb_generation_requires_an_output_target(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="At least one output target"):
        dolphindb_alphas.run_generation(
            _args(tmp_path / "input.parquet", tmp_path / "unused.parquet", output=None),
            ddb_module=FakeDolphinDB(FakeSession()),
        )


def test_dolphindb_generation_can_keep_float64_factors(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    _panel().to_parquet(input_path)

    dolphindb_alphas.run_generation(
        _args(input_path, output_path, factor_dtype="float64"),
        ddb_module=FakeDolphinDB(FakeSession()),
    )

    out = pd.read_parquet(output_path)
    manifest = json.loads(
        output_path.with_suffix(output_path.suffix + ".factor_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert str(out["alpha101_001"].dtype) == "float64"
    assert manifest["factor_dtype"] == "float64"


def test_dolphindb_generation_records_row_group_size(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    _panel().to_parquet(input_path)

    dolphindb_alphas.run_generation(
        _args(input_path, output_path, row_group_size=1),
        ddb_module=FakeDolphinDB(FakeSession()),
    )

    manifest = json.loads(
        output_path.with_suffix(output_path.suffix + ".factor_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["output_data"]["row_group_size"] == 1


def test_dolphindb_generation_script_is_compatibility_wrapper() -> None:
    assert build_dolphindb_alphas.run_generation is dolphindb_alphas.run_generation
    assert build_dolphindb_alphas.main is dolphindb_alphas.main


def test_dolphindb_generation_cli_main_prints_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "out.parquet"
    manifest_path = tmp_path / "out.parquet.factor_manifest.json"

    def fake_run_generation(args: argparse.Namespace) -> dolphindb_alphas.GenerationResult:
        assert args.input == "input.parquet"
        assert args.output == str(output_path)
        return dolphindb_alphas.GenerationResult(
            output_path=output_path,
            manifest_path=manifest_path,
            rows=12,
            alpha_columns=101,
        )

    monkeypatch.setattr(dolphindb_alphas, "run_generation", fake_run_generation)

    exit_code = dolphindb_alphas.main(
        [
            "--input",
            "input.parquet",
            "--output",
            str(output_path),
            "--alpha101",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"Saved panel: {output_path}" in captured.out
    assert "Rows: 12" in captured.out
    assert "Alpha columns: 101" in captured.out


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

    with pytest.raises(RuntimeError, match="external-alphas"):
        build_dolphindb_alphas.load_dolphindb_client()
