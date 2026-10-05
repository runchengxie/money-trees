from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

from moneytree.data_release import (
    DEFAULT_RAW_CACHE_COMPRESSION_LEVEL,
    DEFAULT_RELEASE_MAX_ASSET_SIZE_BYTES,
    build_github_release_upload_command,
    create_data_release,
    resolve_release_output_dir,
    upload_github_release_assets,
)


def _default_max_asset_size_mb() -> float:
    return DEFAULT_RELEASE_MAX_ASSET_SIZE_BYTES / 1024 / 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build GitHub Releases-friendly Money Trees data release assets. "
            "Raw-cache tar compression is optional; factor-store tar assets remain uncompressed."
        )
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help=(
            "Directory for generated release assets. WSL paths like /mnt/d/... and "
            "Windows drive paths like D:/... are supported."
        ),
    )
    parser.add_argument("--panel", help="Optional base date,ticker panel parquet or pickle path.")
    parser.add_argument("--raw-cache", help="Optional TuShare raw cache directory or manifest.sqlite path.")
    parser.add_argument(
        "--raw-cache-compression",
        choices=["none", "zstd"],
        default="none",
        help="Compression for raw-cache tar shards. Zstandard requires the release extra.",
    )
    parser.add_argument(
        "--raw-cache-compression-level",
        type=int,
        default=DEFAULT_RAW_CACHE_COMPRESSION_LEVEL,
        help="Zstandard level for raw-cache tar shards, from 1 to 22. Default: 19.",
    )
    parser.add_argument("--factor-store", help="Optional factor-store directory or manifest.json path.")
    parser.add_argument(
        "--max-asset-size-mb",
        type=float,
        default=_default_max_asset_size_mb(),
        help="Maximum generated asset size in MiB. Default: 1536.",
    )
    parser.add_argument("--label", default="", help="Optional human-readable release label.")
    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="Optional note to include in manifest.json and README.md. Repeatable.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview planned assets without writing files or uploading.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing existing files in --output-dir.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable resumable output reuse; existing files then require --overwrite.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Show packaging progress on stderr.",
    )
    parser.add_argument(
        "--skip-space-check",
        action="store_true",
        help="Skip target filesystem free-space preflight.",
    )
    parser.add_argument("--github-repo", help="GitHub repository in owner/repo form.")
    parser.add_argument("--github-tag", help="Existing or new GitHub release tag.")
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload generated assets with gh release upload.",
    )
    parser.add_argument(
        "--create-release",
        action="store_true",
        help="Create the GitHub release with gh release create before uploading.",
    )
    parser.add_argument("--release-title", help="Optional title when --create-release is used.")
    parser.add_argument(
        "--clobber",
        action="store_true",
        help="Pass --clobber to gh release upload.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format. Default: text.",
    )
    return parser


def _upload_command_or_none(args: argparse.Namespace, upload_paths: tuple[Path, ...]) -> list[str] | None:
    if not args.github_repo or not args.github_tag:
        return None
    return build_github_release_upload_command(
        repo=args.github_repo,
        tag=args.github_tag,
        asset_paths=list(upload_paths),
        clobber=bool(args.clobber),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.upload and (not args.github_repo or not args.github_tag):
        parser.error("--upload requires --github-repo and --github-tag.")
    if args.create_release and not args.upload:
        parser.error("--create-release requires --upload.")

    try:
        result = create_data_release(
            output_dir=resolve_release_output_dir(args.output_dir),
            panel=Path(args.panel) if args.panel else None,
            raw_cache=Path(args.raw_cache) if args.raw_cache else None,
            factor_store=Path(args.factor_store) if args.factor_store else None,
            raw_cache_compression=args.raw_cache_compression,
            raw_cache_compression_level=args.raw_cache_compression_level,
            max_asset_size_bytes=int(args.max_asset_size_mb * 1024 * 1024),
            label=args.label or None,
            notes=list(args.note or ()),
            dry_run=bool(args.dry_run),
            overwrite=bool(args.overwrite),
            check_space=not bool(args.skip_space_check),
            resume=not bool(args.no_resume),
            show_progress=bool(args.progress),
        )
        upload_command = _upload_command_or_none(args, result.upload_paths)
        if args.upload and not args.dry_run:
            upload_github_release_assets(
                repo=args.github_repo,
                tag=args.github_tag,
                asset_paths=list(result.upload_paths),
                create_release=bool(args.create_release),
                release_title=args.release_title,
                notes_file=result.readme_path,
                clobber=bool(args.clobber),
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        payload = {
            "manifest": result.manifest,
            "manifest_path": str(result.manifest_path) if result.manifest_path else None,
            "checksums_path": str(result.checksums_path) if result.checksums_path else None,
            "readme_path": str(result.readme_path) if result.readme_path else None,
            "upload_paths": [str(path) for path in result.upload_paths],
            "upload_command": upload_command,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = result.manifest["asset_summary"]
        action = "Planned" if args.dry_run else "Saved"
        print(
            f"{action} data release assets "
            f"assets={summary['asset_count']} "
            f"upload_assets={summary['total_upload_asset_count']} "
            f"bytes={summary['total_asset_size_bytes']}"
        )
        if result.manifest_path:
            print(f"Manifest: {result.manifest_path}")
        if result.checksums_path:
            print(f"Checksums: {result.checksums_path}")
        if upload_command:
            print(f"Upload command: {shlex.join(upload_command)}")
        if args.upload and not args.dry_run:
            print(f"Uploaded release assets to {args.github_repo} tag={args.github_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
