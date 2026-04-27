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

from moneytree.data import load_market_data, save_market_data
from moneytree.factors.external import (
    build_dolphindb_input,
    build_external_alpha_manifest,
    merge_external_alpha_columns,
    normalize_external_families,
    write_external_alpha_manifest,
)


DEFAULT_ALPHA101_FUNCTION = "calcMoneyTreeAlpha101"
DEFAULT_ALPHA191_FUNCTION = "calcMoneyTreeAlpha191"


@dataclass(frozen=True)
class GenerationResult:
    output_path: Path
    manifest_path: Path
    rows: int
    alpha_columns: int


def _dolphindb_install_message() -> str:
    return (
        "Missing optional DolphinDB Python client. Install it in your current environment "
        "with `uv pip install dolphindb`, or use an environment that already provides "
        "the `dolphindb` package."
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


def _run_setup_script(session: Any, families: Sequence[str]) -> None:
    module_lines: list[str] = []
    if "alpha101" in families:
        module_lines.extend(["use wq101alpha", "use prepare101"])
    if "alpha191" in families:
        module_lines.extend(["use gtja191Alpha", "use gtja191Prepare"])
    module_lines.append("use moneytreeAlpha")

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


def run_generation(args: argparse.Namespace, *, ddb_module: Any | None = None) -> GenerationResult:
    families = _selected_families(args)
    input_path = Path(args.input)
    output_path = Path(args.output)
    manifest_path = (
        Path(args.manifest_output)
        if args.manifest_output
        else output_path.with_suffix(output_path.suffix + ".factor_manifest.json")
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
    session.upload({"rawData": ddb_input})
    _run_setup_script(session, families)

    merged = panel
    validation: dict[str, Any] = {"families": families, "family_results": {}}
    for family in families:
        function_name = _family_function(args, family)
        result = session.run(f"{function_name}(rawData, startTime, endTime)")
        merged, family_validation = merge_external_alpha_columns(merged, result, [family])
        validation["family_results"][family] = family_validation

    alpha_columns = [
        column
        for column in merged.columns
        if str(column).startswith(("alpha101_", "alpha191_"))
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_paths: list[Path] = []

    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as handle:
            temp_output = Path(handle.name)
        temp_paths.append(temp_output)
        save_market_data(merged, temp_output, compression=args.compression)

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

    return GenerationResult(
        output_path=output_path,
        manifest_path=manifest_path,
        rows=int(len(merged)),
        alpha_columns=len(alpha_columns),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate external Alpha101/Alpha191 factors with DolphinDB and merge them into a money-tree panel.",
    )
    parser.add_argument("--input", required=True, help="Input money-tree panel parquet or pickle.")
    parser.add_argument("--output", required=True, help="Output merged panel parquet.")
    parser.add_argument(
        "--manifest-output",
        help="Manifest JSON path. Defaults to <output>.factor_manifest.json.",
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
    parser.add_argument("--compression", default="snappy", help="Parquet compression.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = run_generation(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Saved panel: {result.output_path}")
    print(f"Saved manifest: {result.manifest_path}")
    print(f"Rows: {result.rows:,}")
    print(f"Alpha columns: {result.alpha_columns:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
