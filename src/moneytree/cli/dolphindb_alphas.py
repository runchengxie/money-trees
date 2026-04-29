from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path
import sys
import tempfile
from typing import Any

import pandas as pd

from moneytree.data import (
    DEFAULT_PARQUET_COMPRESSION,
    coerce_factor_columns,
    ensure_date_ticker_index,
    load_market_data,
    normalize_factor_dtype,
    save_market_data,
)
from moneytree.factors.external import (
    build_dolphindb_input,
    build_external_alpha_manifest,
    external_alpha_columns,
    merge_external_alpha_columns,
    normalize_external_families,
    write_external_alpha_manifest,
)
from moneytree.factor_store import (
    write_external_factor_store,
    write_external_factor_store_partitioned,
)


DEFAULT_ALPHA101_FUNCTION = "calcMoneyTreeAlpha101"
DEFAULT_ALPHA191_FUNCTION = "calcMoneyTreeAlpha191"
MODULE_DIR_HINT = "docker/dolphindb/modules/"
MODULE_VERSION_HINT = (
    "`--wq101-module-version`, `--gtja191-module-version`, and "
    "`--moneytree-alpha-module-version` only record manifest metadata; they do not "
    "change DolphinDB `use` module names."
)


@dataclass(frozen=True)
class GenerationResult:
    output_path: Path | None
    manifest_path: Path | None
    rows: int
    alpha_columns: int
    factor_store_manifest_path: Path | None = None


def _dolphindb_install_message() -> str:
    return (
        "Missing optional DolphinDB Python client. Install it in your current environment "
        "with `uv sync --dev --extra external-alphas` or `uv sync --dev --extra research`, "
        "or use an environment that already provides the `dolphindb` package."
    )


def load_dolphindb_client():
    try:
        import dolphindb as ddb  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(_dolphindb_install_message()) from exc
    return ddb


def _package_version(name: str) -> str | None:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None


def _selected_families(args: argparse.Namespace) -> list[str]:
    requested = list(args.family or [])
    if args.alpha101:
        requested.append("alpha101")
    if args.alpha191:
        requested.append("alpha191")
    return normalize_external_families(requested)


def _family_function(args: argparse.Namespace, family: str) -> str:
    if family == "alpha101":
        return args.alpha101_function
    if family == "alpha191":
        return args.alpha191_function
    raise ValueError(f"Unsupported family: {family}")


def _module_versions(args: argparse.Namespace) -> dict[str, str]:
    return {
        "wq101alpha": args.wq101_module_version,
        "gtja191Alpha": args.gtja191_module_version,
        "moneytreeAlpha": args.moneytree_alpha_module_version,
    }


def _required_modules(families: Sequence[str]) -> list[str]:
    modules: list[str] = []
    if "alpha101" in families:
        modules.extend(["wq101alpha", "prepare101"])
    if "alpha191" in families:
        modules.extend(["gtja191Alpha", "gtja191Prepare"])
    modules.append("moneytreeAlpha")
    return list(dict.fromkeys(modules))


def _dolphindb_string_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _dolphindb_date_literal(value: object) -> str:
    return pd.Timestamp(value).strftime("%Y.%m.%d")


def _moneytree_function_ref(function_name: str) -> str:
    if "::" in function_name:
        return function_name
    return f"moneytreeAlpha::{function_name}"


def _empty_result(value: Any) -> bool:
    if value is None:
        return True
    try:
        return len(value) == 0
    except TypeError:
        return not bool(value)


def _preflight_module_error(module_name: str, exc: Exception) -> RuntimeError:
    return RuntimeError(
        "DolphinDB Alpha101/191 preflight failed while loading module "
        f"[{module_name}]. Expected local module file: "
        f"{MODULE_DIR_HINT}{module_name}.dos. When using docker-compose.alpha.yml, "
        "this repository directory is mounted into the DolphinDB server modules "
        f"directory. {MODULE_VERSION_HINT} Original DolphinDB error: {exc}"
    )


def _preflight_function_error(function_name: str, family: str) -> RuntimeError:
    return RuntimeError(
        "DolphinDB Alpha101/191 preflight failed because moneytreeAlpha.dos does "
        f"not expose wrapper function [{function_name}] for {family}. Add the "
        f"function to {MODULE_DIR_HINT}moneytreeAlpha.dos or pass the correct "
        f"--{family}-function value."
    )


def _run_preflight(session: Any, args: argparse.Namespace, families: Sequence[str]) -> None:
    for module_name in _required_modules(families):
        try:
            session.run(f"use {module_name}\n1")
        except Exception as exc:
            raise _preflight_module_error(module_name, exc) from exc

    for family in families:
        function_name = _family_function(args, family)
        function_ref = _moneytree_function_ref(function_name)
        function_literal = _dolphindb_string_literal(function_ref)
        try:
            result = session.run(
                "use moneytreeAlpha\n"
                f"select name from defs({function_literal}) where name = {function_literal}"
            )
        except Exception as exc:
            raise RuntimeError(
                "DolphinDB Alpha101/191 preflight failed while checking wrapper "
                f"function [{function_name}] in moneytreeAlpha.dos. Original "
                f"DolphinDB error: {exc}"
            ) from exc
        if _empty_result(result):
            raise _preflight_function_error(function_name, family)


def _run_setup_script(session: Any, families: Sequence[str]) -> None:
    module_lines = [f"use {module_name}" for module_name in _required_modules(families)]

    session.run(
        "\n".join(module_lines)
        + """
        startTime = min(rawData.tradetime)
        endTime = max(rawData.tradetime)
        """
    )


def _server_version(session: Any) -> str | None:
    try:
        value = session.run("version()")
    except Exception:
        return None
    return str(value) if value is not None else None


def _panel_trade_dates(panel: pd.DataFrame) -> pd.Index:
    indexed = ensure_date_ticker_index(panel)
    return pd.Index(indexed.index.get_level_values("date").unique()).sort_values()


def _family_alpha_column_count(families: Sequence[str]) -> int:
    return sum(len(external_alpha_columns(family)) for family in families)


def _run_dolphindb_family_part(
    session: Any,
    args: argparse.Namespace,
    family: str,
    *,
    all_dates: pd.Index,
    target_dates: pd.Index,
    warmup_trade_dates: int,
) -> pd.DataFrame:
    date_positions = {pd.Timestamp(value): idx for idx, value in enumerate(all_dates)}
    first_target = pd.Timestamp(target_dates[0])
    last_target = pd.Timestamp(target_dates[-1])
    target_start_idx = date_positions[first_target]
    target_end_idx = date_positions[last_target]
    calc_start_idx = max(0, target_start_idx - max(0, int(warmup_trade_dates)))
    calc_dates = all_dates[calc_start_idx : target_end_idx + 1]
    calc_start = pd.Timestamp(calc_dates[0])
    calc_end = pd.Timestamp(calc_dates[-1])
    function_name = _family_function(args, family)

    return session.run(
        f"""
        mtCalcStart = {_dolphindb_date_literal(calc_start)}
        mtCalcEnd = {_dolphindb_date_literal(calc_end)}
        mtTargetStart = {_dolphindb_date_literal(first_target)}
        mtTargetEnd = {_dolphindb_date_literal(last_target)}
        mtChunkRawData = select * from rawData where tradetime between mtCalcStart:mtCalcEnd
        mtChunkResult = {function_name}(mtChunkRawData, mtCalcStart, mtCalcEnd)
        select * from mtChunkResult where tradetime between mtTargetStart:mtTargetEnd
        """
    )


def _write_streamed_factor_store(
    session: Any,
    args: argparse.Namespace,
    *,
    panel: pd.DataFrame,
    input_path: Path,
    families: Sequence[str],
    factor_dtype: str,
    field_mapping: dict[str, Any],
    version: str | None,
) -> Path:
    store_dir = Path(args.factor_store_output)
    all_dates = _panel_trade_dates(panel)
    warmup_trade_dates = int(getattr(args, "dolphindb_warmup_trade_dates", 260))

    def generate_family_part(
        family: str,
        target_dates: pd.Index,
        part_index: int,
        part_count: int,
    ) -> pd.DataFrame:
        del part_index, part_count
        return _run_dolphindb_family_part(
            session,
            args,
            family,
            all_dates=all_dates,
            target_dates=target_dates,
            warmup_trade_dates=warmup_trade_dates,
        )

    write_external_factor_store_partitioned(
        panel,
        store_dir,
        families=families,
        generate_family_part=generate_family_part,
        factor_dtype=factor_dtype,
        chunk_trade_dates=int(getattr(args, "chunk_trade_dates", 60)),
        compression=args.compression,
        compression_level=getattr(args, "compression_level", None),
        row_group_size=getattr(args, "row_group_size", None),
        metadata={
            "source": "moneytrees-dolphindb-alphas",
            "input": str(input_path),
            "families": list(families),
            "field_mapping": field_mapping,
            "dolphindb": {
                "host": args.host,
                "port": int(args.port),
                "user": args.user,
                "server_version": version,
                "python_client_version": _package_version("dolphindb"),
            },
            "module_versions": _module_versions(args),
            "dolphindb_warmup_trade_dates": warmup_trade_dates,
            "row_group_size": getattr(args, "row_group_size", None),
        },
        show_progress=bool(getattr(args, "progress", False)),
    )
    return store_dir / "manifest.json"


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def _nonnegative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def run_generation(args: argparse.Namespace, *, ddb_module: Any | None = None) -> GenerationResult:
    families = _selected_families(args)
    factor_dtype = normalize_factor_dtype(getattr(args, "factor_dtype", "float32"))
    input_path = Path(args.input)
    no_wide_output = bool(getattr(args, "no_wide_output", False))
    factor_store_output = getattr(args, "factor_store_output", None)
    if no_wide_output and not factor_store_output:
        raise ValueError("--no-wide-output requires --factor-store-output.")
    if no_wide_output and getattr(args, "output", None):
        raise ValueError("--no-wide-output cannot be combined with --output.")
    if not getattr(args, "output", None) and not factor_store_output:
        raise ValueError("At least one output target is required: --output or --factor-store-output.")

    output_path = Path(args.output) if getattr(args, "output", None) and not no_wide_output else None
    manifest_path = (
        (
            Path(args.manifest_output)
            if args.manifest_output
            else output_path.with_suffix(output_path.suffix + ".factor_manifest.json")
        )
        if output_path is not None
        else None
    )

    panel = load_market_data(input_path)
    ddb_input, field_mapping = build_dolphindb_input(
        panel,
        families,
        use_adjusted_prices=not args.raw_price_fields,
    )

    ddb = ddb_module if ddb_module is not None else load_dolphindb_client()
    session = ddb.Session()
    session.connect(args.host, int(args.port), args.user, args.password)
    version = _server_version(session)
    _run_preflight(session, args, families)
    session.upload({"rawData": ddb_input})
    _run_setup_script(session, families)

    if no_wide_output and factor_store_output:
        factor_store_manifest_path = _write_streamed_factor_store(
            session,
            args,
            panel=panel,
            input_path=input_path,
            families=families,
            factor_dtype=factor_dtype,
            field_mapping=field_mapping,
            version=version,
        )
        return GenerationResult(
            output_path=None,
            manifest_path=None,
            rows=int(len(panel)),
            alpha_columns=_family_alpha_column_count(families),
            factor_store_manifest_path=factor_store_manifest_path,
        )

    merged = panel
    validation: dict[str, Any] = {"families": families, "family_results": {}}
    for family in families:
        function_name = _family_function(args, family)
        result = session.run(f"{function_name}(rawData, startTime, endTime)")
        merged, family_validation = merge_external_alpha_columns(merged, result, [family])
        validation["family_results"][family] = family_validation
    merged = coerce_factor_columns(merged, factor_dtype)

    alpha_columns = [
        column
        for column in merged.columns
        if str(column).startswith(("alpha101_", "alpha191_"))
    ]

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_paths: list[Path] = []

    try:
        if output_path is not None and manifest_path is not None:
            with tempfile.NamedTemporaryFile(
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                dir=output_path.parent,
                delete=False,
            ) as handle:
                temp_output = Path(handle.name)
            temp_paths.append(temp_output)
            save_market_data(
                merged,
                temp_output,
                compression=args.compression,
                compression_level=getattr(args, "compression_level", None),
                row_group_size=getattr(args, "row_group_size", None),
            )

            manifest = build_external_alpha_manifest(
                input_path=input_path,
                output_path=temp_output,
                input_frame=panel,
                output_frame=merged,
                families=families,
                field_mapping=field_mapping,
                validation=validation,
                dolphindb={
                    "host": args.host,
                    "port": int(args.port),
                    "user": args.user,
                    "password": args.password,
                    "server_version": version,
                    "python_client_version": _package_version("dolphindb"),
                },
                module_versions=_module_versions(args),
            )
            manifest["output_data"]["path"] = str(output_path)
            manifest["output_data"]["compression"] = args.compression
            manifest["output_data"]["compression_level"] = getattr(args, "compression_level", None)
            manifest["output_data"]["row_group_size"] = getattr(args, "row_group_size", None)
            manifest["factor_dtype"] = factor_dtype

            with tempfile.NamedTemporaryFile(
                prefix=f".{manifest_path.name}.",
                suffix=".tmp",
                dir=manifest_path.parent,
                delete=False,
            ) as handle:
                temp_manifest = Path(handle.name)
            temp_paths.append(temp_manifest)
            write_external_alpha_manifest(manifest, temp_manifest)

            temp_output.replace(output_path)
            temp_manifest.replace(manifest_path)
            temp_paths.clear()
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)

    factor_store_manifest_path: Path | None = None
    if factor_store_output:
        store_dir = Path(factor_store_output)
        write_external_factor_store(
            panel,
            merged,
            store_dir,
            families=families,
            factor_dtype=factor_dtype,
            chunk_trade_dates=int(getattr(args, "chunk_trade_dates", 60)),
            compression=args.compression,
            compression_level=getattr(args, "compression_level", None),
            row_group_size=getattr(args, "row_group_size", None),
            metadata={
                "source": "moneytrees-dolphindb-alphas",
                "input": str(input_path),
                "families": families,
                "field_mapping": field_mapping,
                "validation": validation,
                "dolphindb": {
                    "host": args.host,
                    "port": int(args.port),
                    "user": args.user,
                    "server_version": version,
                    "python_client_version": _package_version("dolphindb"),
                },
                "module_versions": _module_versions(args),
                "row_group_size": getattr(args, "row_group_size", None),
            },
            show_progress=bool(getattr(args, "progress", False)),
        )
        factor_store_manifest_path = store_dir / "manifest.json"

    return GenerationResult(
        output_path=output_path,
        manifest_path=manifest_path,
        rows=int(len(merged)),
        alpha_columns=len(alpha_columns),
        factor_store_manifest_path=factor_store_manifest_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate external Alpha101/Alpha191 factors with DolphinDB and merge them "
            "into a Money Trees panel."
        ),
    )
    parser.add_argument("--input", required=True, help="Input Money Trees panel parquet or pickle.")
    parser.add_argument("--output", help="Output merged panel parquet.")
    parser.add_argument(
        "--manifest-output",
        help="Manifest JSON path. Defaults to <output>.factor_manifest.json.",
    )
    parser.add_argument(
        "--factor-store-output",
        help="Output factor-store directory for generated Alpha101/191 families.",
    )
    parser.add_argument(
        "--no-wide-output",
        action="store_true",
        help="Write only --factor-store-output and skip the merged wide panel.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="DolphinDB host.")
    parser.add_argument("--port", type=int, default=8848, help="DolphinDB port.")
    parser.add_argument("--user", default="admin", help="DolphinDB user.")
    parser.add_argument("--password", default="123456", help="DolphinDB password.")
    parser.add_argument(
        "--family",
        action="append",
        choices=["alpha101", "alpha191"],
        help="External factor family to generate. Can be passed multiple times.",
    )
    parser.add_argument("--alpha101", action="store_true", help="Generate Alpha101.")
    parser.add_argument("--alpha191", action="store_true", help="Generate Alpha191.")
    parser.add_argument(
        "--raw-price-fields",
        action="store_true",
        help="Use raw OHLCV/VWAP fields instead of adjusted price fields when both exist.",
    )
    parser.add_argument(
        "--alpha101-function",
        default=DEFAULT_ALPHA101_FUNCTION,
        help="DolphinDB wrapper function returning Alpha101 table.",
    )
    parser.add_argument(
        "--alpha191-function",
        default=DEFAULT_ALPHA191_FUNCTION,
        help="DolphinDB wrapper function returning Alpha191 table.",
    )
    parser.add_argument("--wq101-module-version", default="unknown")
    parser.add_argument("--gtja191-module-version", default="unknown")
    parser.add_argument("--moneytree-alpha-module-version", default="unknown")
    parser.add_argument(
        "--factor-dtype",
        default="float32",
        choices=["float32", "float64"],
        help="Dtype for generated Alpha101/191 columns in the output parquet.",
    )
    parser.add_argument(
        "--compression",
        default=DEFAULT_PARQUET_COMPRESSION,
        help="Parquet compression.",
    )
    parser.add_argument(
        "--compression-level",
        type=int,
        default=None,
        help="Parquet compression level. Defaults to 3 for zstd.",
    )
    parser.add_argument(
        "--row-group-size",
        type=_positive_int,
        default=None,
        help="Optional parquet row group size in rows.",
    )
    parser.add_argument(
        "--chunk-trade-dates",
        type=_positive_int,
        default=60,
        help=(
            "Number of target trade dates per factor-store partition. In "
            "--no-wide-output mode this also controls each DolphinDB calculation chunk."
        ),
    )
    parser.add_argument(
        "--dolphindb-warmup-trade-dates",
        type=_nonnegative_int,
        default=260,
        help=(
            "Historical trade dates included before each streamed DolphinDB calculation "
            "chunk so rolling Alpha101/191 formulas have lookback context."
        ),
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print factor-store partition write progress to stderr.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = run_generation(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if result.output_path is not None:
        print(f"Saved panel: {result.output_path}")
    if result.manifest_path is not None:
        print(f"Saved manifest: {result.manifest_path}")
    if result.factor_store_manifest_path is not None:
        print(f"Saved factor store: {result.factor_store_manifest_path}")
    print(f"Rows: {result.rows:,}")
    print(f"Alpha columns: {result.alpha_columns:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
