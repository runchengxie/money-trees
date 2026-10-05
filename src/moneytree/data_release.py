from __future__ import annotations

import json
import math
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
from tarfile import ExtractError
from typing import Any

from moneytree._factor_store_manifest import read_factor_store_manifest
from moneytree.data_snapshot import _git_metadata, _panel_summary
from moneytree.metadata import file_metadata, sha256_file

DATA_RELEASE_SCHEMA_VERSION = "1.1"
DATA_RELEASE_KIND = "moneytree_data_release"
GITHUB_RELEASE_ASSET_LIMIT = 1000
GITHUB_RELEASE_MAX_ASSET_SIZE_BYTES = 2 * 1024**3
DEFAULT_RELEASE_MAX_ASSET_SIZE_BYTES = 1536 * 1024**2
DEFAULT_RAW_CACHE_COMPRESSION_LEVEL = 19
DEFAULT_RAW_CACHE_ZSTD_WINDOW_LOG = 27
_METADATA_ASSET_COUNT = 3
_IO_CHUNK_SIZE = 1024 * 1024
_WINDOWS_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/]*(.*)$")


@dataclass(frozen=True)
class ReleaseSourceFile:
    path: Path
    archive_path: str
    role: str
    size_bytes: int


@dataclass(frozen=True)
class DataReleaseResult:
    manifest_path: Path | None
    checksums_path: Path | None
    readme_path: Path | None
    upload_paths: tuple[Path, ...]
    manifest: dict[str, Any]


class DataReleaseProgress:
    def __init__(self, *, enabled: bool, total_bytes: int) -> None:
        self.enabled = bool(enabled)
        self.total_bytes = max(1, int(total_bytes))
        self.completed_bytes = 0
        self._last_rendered_at = 0.0
        self._active_message = ""

    def start(self, message: str) -> None:
        self._active_message = message
        self._render(force=True)

    def advance(self, bytes_count: int, *, message: str | None = None) -> None:
        self.completed_bytes += max(0, int(bytes_count))
        if message is not None:
            self._active_message = message
        self._render()

    def finish_asset(self, message: str) -> None:
        self._active_message = message
        self._render(force=True)

    def finish_all(self) -> None:
        if not self.enabled:
            return
        self.completed_bytes = self.total_bytes
        self._active_message = "done"
        self._render(force=True)
        print(file=sys.stderr, flush=True)

    def _render(self, *, force: bool = False) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        if not force and now - self._last_rendered_at < 0.5:
            return
        self._last_rendered_at = now
        completed = min(self.completed_bytes, self.total_bytes)
        percent = completed / self.total_bytes
        line = (
            "\r"
            f"[data-release] {_progress_bar(completed, self.total_bytes)} "
            f"{percent:6.2%} {_format_bytes(completed)}/{_format_bytes(self.total_bytes)} "
            f"{self._active_message}"
        )
        print(line, end="", file=sys.stderr, flush=True)


class _ProgressFileReader:
    def __init__(
        self,
        handle: Any,
        *,
        progress: DataReleaseProgress,
        message: str,
    ) -> None:
        self.handle = handle
        self.progress = progress
        self.message = message

    def read(self, size: int = -1) -> bytes:
        chunk = self.handle.read(size)
        if chunk:
            self.progress.advance(len(chunk), message=self.message)
        return chunk


def _is_wsl() -> bool:
    """Return True when running inside Windows Subsystem for Linux."""
    try:
        return "microsoft" in platform.uname().release.lower()
    except Exception:
        return False


def resolve_release_output_dir(path: str | Path) -> Path:
    """Resolve a release output directory for the current platform.

    Inside WSL a Windows-style drive path is mapped to its native mount path,
    for example ``C:\\releases`` becomes ``/mnt/c/releases``. On native Windows
    the path is kept unchanged. On other POSIX systems a Windows-style drive
    path keeps its drive letter while backslashes are normalized to forward
    slashes so the returned path is a well-formed POSIX path.
    """
    raw = str(path)
    match = _WINDOWS_DRIVE_RE.match(raw)
    if not match:
        return Path(path).expanduser()
    if not _is_wsl():
        drive = match.group(1)
        rest = match.group(2).replace("\\", "/").lstrip("/")
        normalized = f"{drive}:/{rest}"
        return Path(normalized).expanduser()

    drive = match.group(1).lower()
    rest = match.group(2).replace("\\", "/")
    output_path = Path("/mnt") / drive
    for part in rest.split("/"):
        if part:
            output_path /= part
    return output_path


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_asset_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in value)
    return safe.strip("._") or "asset"


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(max(0, int(value)))
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024.0
    return f"{int(value)}B"


def _progress_bar(current: int, total: int, *, width: int = 24) -> str:
    if total <= 0:
        return f"[{'-' * width}]"
    filled = min(width, max(0, round(width * int(current) / int(total))))
    return f"[{'#' * filled}{'-' * (width - filled)}]"


def _normalize_archive_path(value: str) -> str:
    path = PurePosixPath(str(value).replace("\\", "/"))
    if path.is_absolute():
        path = PurePosixPath(*path.parts[1:])
    parts = [part for part in path.parts if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"Unsafe archive path: {value}")
    return str(PurePosixPath(*parts))


def _reject_sensitive_path(path: Path) -> None:
    if any(part == ".env" for part in path.parts):
        raise ValueError(f"Refusing to package sensitive file path: {path}")


def _require_file(path: Path, *, description: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{description} does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"{description} is not a file: {path}")
    _reject_sensitive_path(path)
    return path


def _source_file(path: Path, *, archive_path: str, role: str) -> ReleaseSourceFile:
    file_path = _require_file(path, description=role)
    return ReleaseSourceFile(
        path=file_path,
        archive_path=_normalize_archive_path(archive_path),
        role=role,
        size_bytes=int(file_path.stat().st_size),
    )


def _iter_directory_sources(root: Path, *, role: str, archive_root: str) -> list[ReleaseSourceFile]:
    if not root.exists():
        raise FileNotFoundError(f"{role} path does not exist: {root}")
    if not root.is_dir():
        return [
            _source_file(
                root,
                archive_path=f"{archive_root}/{root.name}",
                role=role,
            )
        ]

    sources: list[ReleaseSourceFile] = []
    for child in sorted(root.rglob("*")):
        if not child.is_file():
            continue
        _reject_sensitive_path(child)
        sources.append(
            _source_file(
                child,
                archive_path=f"{archive_root}/{child.relative_to(root).as_posix()}",
                role=role,
            )
        )
    return sources


def _resolve_store_path(root: Path, raw_path: object) -> Path:
    path = Path(str(raw_path))
    return path if path.is_absolute() else root / path


def _factor_store_manifest_path(path: Path) -> Path:
    return path / "manifest.json" if path.is_dir() else path


def _factor_store_archive_path(raw_path: object) -> str:
    path = PurePosixPath(str(raw_path).replace("\\", "/"))
    if path.is_absolute():
        return f"factor_store/external/{path.name}"
    return f"factor_store/{path.as_posix()}"


def _factor_store_sources(path: Path) -> list[ReleaseSourceFile]:
    manifest_path = _factor_store_manifest_path(path)
    manifest = read_factor_store_manifest(manifest_path)
    root = manifest_path.parent
    sources = [
        _source_file(
            manifest_path,
            archive_path="factor_store/manifest.json",
            role="factor_store",
        )
    ]

    base_panel = manifest.get("base_panel", {}).get("path")
    if base_panel:
        sources.append(
            _source_file(
                _resolve_store_path(root, base_panel),
                archive_path=_factor_store_archive_path(base_panel),
                role="factor_store",
            )
        )

    families = manifest.get("factor_families", {})
    for entry in families.values():
        if not isinstance(entry, dict):
            continue
        raw_paths = list(entry.get("paths") or [])
        if not raw_paths and entry.get("path"):
            raw_paths = [entry["path"]]
        for raw_path in raw_paths:
            sources.append(
                _source_file(
                    _resolve_store_path(root, raw_path),
                    archive_path=_factor_store_archive_path(raw_path),
                    role="factor_store",
                )
            )
    return _dedupe_sources(sources)


def _dedupe_sources(sources: list[ReleaseSourceFile]) -> list[ReleaseSourceFile]:
    found: set[tuple[Path, str]] = set()
    deduped: list[ReleaseSourceFile] = []
    for source in sources:
        key = (source.path.resolve(strict=False), source.archive_path)
        if key in found:
            continue
        found.add(key)
        deduped.append(source)
    return deduped


def _validate_max_asset_size(max_asset_size_bytes: int) -> None:
    if max_asset_size_bytes <= 0:
        raise ValueError("max_asset_size_bytes must be positive.")
    if max_asset_size_bytes >= GITHUB_RELEASE_MAX_ASSET_SIZE_BYTES:
        raise ValueError("max_asset_size_bytes must be under 2 GiB for GitHub Releases.")


def _require_zstandard() -> Any:
    try:
        import zstandard
    except ImportError as exc:
        raise RuntimeError(
            "Zstandard raw-cache packaging requires the release extra: "
            "install with `uv sync --extra release`."
        ) from exc
    return zstandard


def _validate_raw_cache_compression(compression: str, level: int) -> None:
    if compression not in {"none", "zstd"}:
        raise ValueError("raw_cache_compression must be 'none' or 'zstd'.")
    if not 1 <= level <= 22:
        raise ValueError("raw_cache_compression_level must be between 1 and 22.")


def _ensure_can_write(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {path}. Use --overwrite to replace it.")


def _remove_existing_output(path: Path) -> None:
    if path.exists():
        path.unlink()


def _sha256_segment(path: Path, *, byte_start: int, size_bytes: int) -> str:
    digest = sha256()
    remaining = max(0, int(size_bytes))
    with path.open("rb") as handle:
        handle.seek(int(byte_start))
        while remaining:
            chunk = handle.read(min(_IO_CHUNK_SIZE, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def _file_matches_source(output_path: Path, source: ReleaseSourceFile) -> bool:
    if not output_path.exists() or int(output_path.stat().st_size) != source.size_bytes:
        return False
    return sha256_file(output_path) == sha256_file(source.path)


def _file_matches_source_segment(
    output_path: Path,
    source: ReleaseSourceFile,
    *,
    byte_start: int,
    size_bytes: int,
) -> bool:
    if not output_path.exists() or int(output_path.stat().st_size) != int(size_bytes):
        return False
    return sha256_file(output_path) == _sha256_segment(
        source.path,
        byte_start=byte_start,
        size_bytes=size_bytes,
    )


def _tar_member_hash(tar: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    handle = tar.extractfile(member)
    if handle is None:
        raise ExtractError(f"cannot read tar member: {member.name}")
    digest = sha256()
    with handle:
        for chunk in iter(lambda: handle.read(_IO_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tar_matches_sources(output_path: Path, sources: list[ReleaseSourceFile]) -> bool:
    if not output_path.exists() or not output_path.is_file():
        return False
    try:
        with tarfile.open(output_path, "r") as tar:
            members = {member.name: member for member in tar.getmembers() if member.isfile()}
            for source in sources:
                member = members.get(source.archive_path)
                if member is None or int(member.size) != source.size_bytes:
                    return False
                if _tar_member_hash(tar, member) != sha256_file(source.path):
                    return False
    except Exception:
        return False
    return True


def _compressed_tar_matches_sources(
    output_path: Path,
    sources: list[ReleaseSourceFile],
) -> bool:
    if not output_path.exists() or not output_path.is_file():
        return False
    zstandard = _require_zstandard()
    expected = {source.archive_path: source for source in sources}
    found: set[str] = set()
    try:
        with output_path.open("rb") as compressed:
            with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
                with tarfile.open(fileobj=reader, mode="r|") as archive:
                    for member in archive:
                        if not member.isfile():
                            continue
                        source = expected.get(member.name)
                        if source is None or member.size != source.size_bytes:
                            return False
                        if _tar_member_hash(archive, member) != sha256_file(source.path):
                            return False
                        found.add(member.name)
                while reader.read(_IO_CHUNK_SIZE):
                    pass
        return found == set(expected)
    except Exception:
        return False


def _source_payload(source: ReleaseSourceFile, *, compute_hash: bool) -> dict[str, Any]:
    return {
        "path": str(source.path),
        "archive_path": source.archive_path,
        "role": source.role,
        "size_bytes": source.size_bytes,
        "sha256": sha256_file(source.path) if compute_hash else None,
    }


def _asset_payload(
    *,
    output_path: Path,
    output_dir: Path,
    role: str,
    asset_type: str,
    size_bytes: int | None,
    compute_hash: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "name": output_path.name,
        "path": str(output_path),
        "relative_path": output_path.relative_to(output_dir).as_posix(),
        "role": role,
        "type": asset_type,
        "size_bytes": size_bytes,
        "sha256": sha256_file(output_path) if compute_hash and output_path.exists() else None,
    }
    if extra:
        payload.update(extra)
    return payload


def _write_split_parts(
    source: ReleaseSourceFile,
    *,
    output_dir: Path,
    max_asset_size_bytes: int,
    dry_run: bool,
    overwrite: bool,
    resume: bool,
    progress: DataReleaseProgress,
) -> list[dict[str, Any]]:
    part_count = max(1, math.ceil(source.size_bytes / max_asset_size_bytes))
    width = max(3, len(str(part_count)))
    base_name = _safe_asset_name(f"{source.role}__{source.path.name}")
    records: list[dict[str, Any]] = []
    source_sha256 = None if dry_run else sha256_file(source.path)

    if dry_run:
        for index in range(part_count):
            byte_start = index * max_asset_size_bytes
            byte_end = min(source.size_bytes, byte_start + max_asset_size_bytes)
            output_path = output_dir / (
                f"{base_name}.part{index + 1:0{width}d}of{part_count:0{width}d}"
            )
            records.append(
                _asset_payload(
                    output_path=output_path,
                    output_dir=output_dir,
                    role=source.role,
                    asset_type="split_part",
                    size_bytes=byte_end - byte_start,
                    compute_hash=False,
                    extra={
                        "split": {
                            "archive_path": source.archive_path,
                            "source_path": str(source.path),
                            "source_size_bytes": source.size_bytes,
                            "source_sha256": None,
                            "part_index": index + 1,
                            "part_count": part_count,
                            "byte_start": byte_start,
                            "byte_end_exclusive": byte_end,
                        }
                    },
                )
            )
        return records

    with source.path.open("rb") as input_handle:
        for index in range(part_count):
            byte_start = index * max_asset_size_bytes
            part_size = min(max_asset_size_bytes, source.size_bytes - byte_start)
            output_path = output_dir / (
                f"{base_name}.part{index + 1:0{width}d}of{part_count:0{width}d}"
            )
            resume_status = "written"
            if (
                not overwrite
                and resume
                and _file_matches_source_segment(
                    output_path,
                    source,
                    byte_start=byte_start,
                    size_bytes=part_size,
                )
            ):
                input_handle.seek(byte_start + part_size)
                progress.advance(part_size, message=f"reused {output_path.name}")
                resume_status = "reused"
            else:
                if output_path.exists() and (overwrite or resume):
                    _remove_existing_output(output_path)
                _ensure_can_write(output_path, overwrite=overwrite)
                progress.start(f"writing {output_path.name}")
                remaining = part_size
                with output_path.open("wb") as output_handle:
                    while remaining:
                        chunk = input_handle.read(min(_IO_CHUNK_SIZE, remaining))
                        if not chunk:
                            break
                        output_handle.write(chunk)
                        remaining -= len(chunk)
                        progress.advance(len(chunk), message=f"writing {output_path.name}")
                progress.finish_asset(f"wrote {output_path.name}")
            records.append(
                _asset_payload(
                    output_path=output_path,
                    output_dir=output_dir,
                    role=source.role,
                    asset_type="split_part",
                    size_bytes=int(output_path.stat().st_size),
                    compute_hash=True,
                    extra={
                        "split": {
                            "archive_path": source.archive_path,
                            "source_path": str(source.path),
                            "source_size_bytes": source.size_bytes,
                            "source_sha256": source_sha256,
                            "part_index": index + 1,
                            "part_count": part_count,
                            "byte_start": byte_start,
                            "byte_end_exclusive": byte_start + part_size,
                        },
                        "resume_status": resume_status,
                    },
                )
            )
    return records


def _write_direct_file(
    source: ReleaseSourceFile,
    *,
    output_dir: Path,
    dry_run: bool,
    overwrite: bool,
    resume: bool,
    progress: DataReleaseProgress,
) -> dict[str, Any]:
    output_path = output_dir / _safe_asset_name(f"{source.role}__{source.path.name}")
    resume_status = "planned" if dry_run else "written"
    if not dry_run:
        if not overwrite and resume and _file_matches_source(output_path, source):
            progress.advance(source.size_bytes, message=f"reused {output_path.name}")
            resume_status = "reused"
        else:
            if output_path.exists() and (overwrite or resume):
                _remove_existing_output(output_path)
            _ensure_can_write(output_path, overwrite=overwrite)
            progress.start(f"writing {output_path.name}")
            with source.path.open("rb") as input_handle, output_path.open("wb") as output_handle:
                for chunk in iter(lambda: input_handle.read(_IO_CHUNK_SIZE), b""):
                    output_handle.write(chunk)
                    progress.advance(len(chunk), message=f"writing {output_path.name}")
            shutil.copystat(source.path, output_path)
            progress.finish_asset(f"wrote {output_path.name}")
    return _asset_payload(
        output_path=output_path,
        output_dir=output_dir,
        role=source.role,
        asset_type="file",
        size_bytes=source.size_bytes,
        compute_hash=not dry_run,
        extra={
            "contents": [_source_payload(source, compute_hash=not dry_run)],
            "resume_status": resume_status,
        },
    )


def _tar_entry_estimate(size_bytes: int) -> int:
    data_blocks = math.ceil(size_bytes / 512) * 512 if size_bytes else 0
    return 512 + data_blocks


def _tar_file_estimate(sources: list[ReleaseSourceFile]) -> int:
    return 10 * 1024 + sum(_tar_entry_estimate(source.size_bytes) for source in sources)


def _estimated_asset_bytes(
    *,
    panel_sources: list[ReleaseSourceFile],
    raw_cache_sources: list[ReleaseSourceFile],
    factor_store_sources: list[ReleaseSourceFile],
    max_asset_size_bytes: int,
) -> int:
    total = sum(source.size_bytes for source in panel_sources)
    for sources in (raw_cache_sources, factor_store_sources):
        groups, oversized = _tar_groups(sources, max_asset_size_bytes=max_asset_size_bytes)
        total += sum(_tar_file_estimate(group) for group in groups)
        total += sum(source.size_bytes for source in oversized)
    return int(total)


def _source_work_bytes(
    *,
    panel_sources: list[ReleaseSourceFile],
    raw_cache_sources: list[ReleaseSourceFile],
    factor_store_sources: list[ReleaseSourceFile],
) -> int:
    return int(
        sum(source.size_bytes for source in panel_sources)
        + sum(source.size_bytes for source in raw_cache_sources)
        + sum(source.size_bytes for source in factor_store_sources)
    )


def _existing_parent(path: Path) -> Path:
    current = path if path.exists() else path.parent
    while not current.exists() and current.parent != current:
        current = current.parent
    return current if current.exists() else Path.cwd()


def _disk_free_bytes(path: Path) -> int:
    return int(shutil.disk_usage(_existing_parent(path)).free)


def _check_output_space(path: Path, *, required_bytes: int) -> dict[str, Any]:
    free_bytes = _disk_free_bytes(path)
    if free_bytes < required_bytes:
        raise RuntimeError(
            "Not enough free space on output filesystem: "
            f"required~={required_bytes} bytes available={free_bytes} bytes. "
            "Use a larger target such as --output-dir /mnt/d/... or pass --skip-space-check."
        )
    return {
        "checked": True,
        "required_bytes_estimate": int(required_bytes),
        "available_bytes": int(free_bytes),
        "path_checked": str(_existing_parent(path)),
    }


def _tar_groups(
    sources: list[ReleaseSourceFile],
    *,
    max_asset_size_bytes: int,
) -> tuple[list[list[ReleaseSourceFile]], list[ReleaseSourceFile]]:
    groups: list[list[ReleaseSourceFile]] = []
    oversized: list[ReleaseSourceFile] = []
    current: list[ReleaseSourceFile] = []
    current_size = 1024

    for source in sources:
        entry_size = _tar_entry_estimate(source.size_bytes)
        if entry_size + 1024 > max_asset_size_bytes:
            oversized.append(source)
            continue
        if current and current_size + entry_size + 1024 > max_asset_size_bytes:
            groups.append(current)
            current = []
            current_size = 1024
        current.append(source)
        current_size += entry_size
    if current:
        groups.append(current)
    return groups, oversized


def _add_tar_file(
    tar: tarfile.TarFile,
    source: ReleaseSourceFile,
    *,
    progress: DataReleaseProgress,
    asset_name: str,
) -> None:
    stat = source.path.stat()
    info = tarfile.TarInfo(source.archive_path)
    info.size = int(stat.st_size)
    info.mtime = 0
    info.mode = 0o644
    with source.path.open("rb") as handle:
        tar.addfile(
            info,
            _ProgressFileReader(
                handle,
                progress=progress,
                message=f"writing {asset_name}:{source.archive_path}",
            ),
        )


def _write_tar_assets(
    *,
    role: str,
    sources: list[ReleaseSourceFile],
    output_dir: Path,
    max_asset_size_bytes: int,
    dry_run: bool,
    overwrite: bool,
    resume: bool,
    progress: DataReleaseProgress,
    compression: str = "none",
    compression_level: int = 19,
) -> list[dict[str, Any]]:
    grouping_limit = max_asset_size_bytes
    if compression == "zstd":
        grouping_limit = max(
            1,
            max_asset_size_bytes - max(max_asset_size_bytes // 100, 16 * 1024),
        )
    groups, oversized = _tar_groups(sources, max_asset_size_bytes=grouping_limit)
    records: list[dict[str, Any]] = []
    width = max(3, len(str(len(groups))))

    for index, group in enumerate(groups, start=1):
        if compression == "zstd":
            output_path = output_dir / (
                f"{_safe_asset_name(role)}_zstd{compression_level}_part"
                f"{index:0{width}d}.tar.zst"
            )
        else:
            output_path = output_dir / f"{_safe_asset_name(role)}_part{index:0{width}d}.tar"
        resume_status = "planned" if dry_run else "written"
        if not dry_run:
            matches = False
            if not overwrite and resume:
                matches = (
                    _compressed_tar_matches_sources(output_path, group)
                    if compression == "zstd"
                    else _tar_matches_sources(output_path, group)
                )
            if not overwrite and resume and matches:
                progress.advance(
                    sum(source.size_bytes for source in group),
                    message=f"reused {output_path.name}",
                )
                resume_status = "reused"
                actual_size = int(output_path.stat().st_size)
            else:
                if output_path.exists() and (overwrite or resume):
                    _remove_existing_output(output_path)
                _ensure_can_write(output_path, overwrite=overwrite)
                progress.start(f"writing {output_path.name}")
                if compression == "zstd":
                    zstandard = _require_zstandard()
                    parameters = zstandard.ZstdCompressionParameters.from_level(
                        compression_level,
                        window_log=DEFAULT_RAW_CACHE_ZSTD_WINDOW_LOG,
                        enable_ldm=True,
                        write_checksum=1,
                        write_content_size=0,
                    )
                    compressor = zstandard.ZstdCompressor(compression_params=parameters)
                    with output_path.open("wb") as compressed:
                        with compressor.stream_writer(compressed, closefd=False) as writer:
                            with tarfile.open(fileobj=writer, mode="w|") as tar:
                                for source in group:
                                    _add_tar_file(
                                        tar,
                                        source,
                                        progress=progress,
                                        asset_name=output_path.name,
                                    )
                else:
                    with tarfile.open(output_path, "w") as tar:
                        for source in group:
                            _add_tar_file(
                                tar,
                                source,
                                progress=progress,
                                asset_name=output_path.name,
                            )
                actual_size = int(output_path.stat().st_size)
                if actual_size > max_asset_size_bytes:
                    _remove_existing_output(output_path)
                    raise RuntimeError(
                        f"Generated asset exceeds max_asset_size_bytes: {output_path.name} "
                        f"({actual_size} > {max_asset_size_bytes})."
                    )
                progress.finish_asset(f"wrote {output_path.name}")
        else:
            actual_size = _tar_file_estimate(group)
        records.append(
            _asset_payload(
                output_path=output_path,
                output_dir=output_dir,
                role=role,
                asset_type="tar",
                size_bytes=actual_size,
                compute_hash=not dry_run,
                extra={
                    "compression": compression,
                    "compression_level": compression_level if compression == "zstd" else None,
                    "window_log": (
                        DEFAULT_RAW_CACHE_ZSTD_WINDOW_LOG if compression == "zstd" else None
                    ),
                    "size_is_estimate": bool(dry_run and compression == "zstd"),
                    "contents": [
                        _source_payload(source, compute_hash=not dry_run) for source in group
                    ],
                    "resume_status": resume_status,
                },
            )
        )

    for source in oversized:
        records.extend(
            _write_split_parts(
                source,
                output_dir=output_dir,
                max_asset_size_bytes=max_asset_size_bytes,
                dry_run=dry_run,
                overwrite=overwrite,
                resume=resume,
                progress=progress,
            )
        )
    return records


def _write_checksums(path: Path, entries: list[dict[str, Any]], *, overwrite: bool) -> None:
    _ensure_can_write(path, overwrite=overwrite)
    lines = [
        f"{entry['sha256']}  {entry['relative_path']}" for entry in entries if entry.get("sha256")
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_readme(path: Path, manifest: dict[str, Any], *, overwrite: bool) -> None:
    _ensure_can_write(path, overwrite=overwrite)
    summary = manifest["asset_summary"]
    lines = [
        "# Money Trees Data Release",
        "",
        f"- Created at UTC: {manifest['created_at_utc']}",
        f"- Asset count: {summary['asset_count']}",
        f"- Total asset bytes: {summary['total_asset_size_bytes']}",
        f"- Max asset size bytes: {manifest['max_asset_size_bytes']}",
        "- Raw-cache tar compression: "
        + (
            "Zstandard level "
            f"{manifest['packaging']['raw_cache_compression_level']} "
            f"(window log {manifest['packaging']['raw_cache_zstd_window_log']})"
            if manifest["packaging"]["raw_cache_compression"] == "zstd"
            else "none"
        ),
        "- Factor-store tar compression: none",
    ]
    if manifest.get("label"):
        lines.append(f"- Label: {manifest['label']}")
    if manifest.get("notes"):
        lines.extend(["", "## Notes", "", *[f"- {note}" for note in manifest["notes"]]])
    lines.extend(
        [
            "",
            "## Restore",
            "",
            "- Verify downloaded files with `sha256sum -c sha256sums.txt`.",
            "- Extract uncompressed `*_partNNN.tar` assets with `tar -xf <asset>.tar`.",
            "- Extract `*.tar.zst` assets with `zstd -d -c <asset>.tar.zst | tar -xf -`.",
            "- Recombine split files in part order with `cat <name>.part* > <restored-file>`.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _collect_sources(
    *,
    panel: Path | None,
    raw_cache: Path | None,
    factor_store: Path | None,
) -> tuple[list[ReleaseSourceFile], list[ReleaseSourceFile], list[ReleaseSourceFile]]:
    panel_sources = (
        [_source_file(panel, archive_path=f"panel/{panel.name}", role="panel")]
        if panel is not None
        else []
    )
    raw_cache_sources = (
        _iter_directory_sources(raw_cache, role="raw_cache", archive_root="raw_cache")
        if raw_cache is not None
        else []
    )
    factor_store_sources = _factor_store_sources(factor_store) if factor_store is not None else []
    return panel_sources, _dedupe_sources(raw_cache_sources), _dedupe_sources(factor_store_sources)


def create_data_release(
    *,
    output_dir: str | Path,
    panel: str | Path | None = None,
    raw_cache: str | Path | None = None,
    factor_store: str | Path | None = None,
    raw_cache_compression: str = "none",
    raw_cache_compression_level: int = DEFAULT_RAW_CACHE_COMPRESSION_LEVEL,
    max_asset_size_bytes: int = DEFAULT_RELEASE_MAX_ASSET_SIZE_BYTES,
    label: str | None = None,
    notes: list[str] | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
    check_space: bool = True,
    resume: bool = True,
    show_progress: bool = False,
) -> DataReleaseResult:
    """Build GitHub Releases-friendly data assets and a release manifest."""
    _validate_max_asset_size(int(max_asset_size_bytes))
    _validate_raw_cache_compression(raw_cache_compression, int(raw_cache_compression_level))
    if raw_cache_compression == "zstd":
        _require_zstandard()
        if raw_cache is None:
            raise ValueError("raw_cache_compression requires a raw_cache input.")
    output_path = resolve_release_output_dir(output_dir)
    panel_path = Path(panel) if panel is not None else None
    raw_cache_path = Path(raw_cache) if raw_cache is not None else None
    factor_store_path = Path(factor_store) if factor_store is not None else None
    if panel_path is None and raw_cache_path is None and factor_store_path is None:
        raise ValueError("At least one of panel, raw_cache, or factor_store is required.")

    panel_sources, raw_cache_sources, factor_store_sources = _collect_sources(
        panel=panel_path,
        raw_cache=raw_cache_path,
        factor_store=factor_store_path,
    )
    required_output_size = _estimated_asset_bytes(
        panel_sources=panel_sources,
        raw_cache_sources=raw_cache_sources,
        factor_store_sources=factor_store_sources,
        max_asset_size_bytes=int(max_asset_size_bytes),
    )
    progress = DataReleaseProgress(
        enabled=show_progress and not dry_run,
        total_bytes=_source_work_bytes(
            panel_sources=panel_sources,
            raw_cache_sources=raw_cache_sources,
            factor_store_sources=factor_store_sources,
        ),
    )
    space_check = {
        "checked": False,
        "required_bytes_estimate": required_output_size,
        "available_bytes": _disk_free_bytes(output_path),
        "path_checked": str(_existing_parent(output_path)),
    }
    if check_space and not dry_run:
        space_check = _check_output_space(output_path, required_bytes=required_output_size)
    if not dry_run:
        output_path.mkdir(parents=True, exist_ok=True)

    assets: list[dict[str, Any]] = []
    for source in panel_sources:
        if source.size_bytes > max_asset_size_bytes:
            assets.extend(
                _write_split_parts(
                    source,
                    output_dir=output_path,
                    max_asset_size_bytes=max_asset_size_bytes,
                    dry_run=dry_run,
                    overwrite=overwrite,
                    resume=resume,
                    progress=progress,
                )
            )
        else:
            assets.append(
                _write_direct_file(
                    source,
                    output_dir=output_path,
                    dry_run=dry_run,
                    overwrite=overwrite,
                    resume=resume,
                    progress=progress,
                )
            )
    if raw_cache_sources:
        assets.extend(
            _write_tar_assets(
                role="raw_cache",
                sources=raw_cache_sources,
                output_dir=output_path,
                max_asset_size_bytes=max_asset_size_bytes,
                dry_run=dry_run,
                overwrite=overwrite,
                resume=resume,
                progress=progress,
                compression=raw_cache_compression,
                compression_level=int(raw_cache_compression_level),
            )
        )
    if factor_store_sources:
        assets.extend(
            _write_tar_assets(
                role="factor_store",
                sources=factor_store_sources,
                output_dir=output_path,
                max_asset_size_bytes=max_asset_size_bytes,
                dry_run=dry_run,
                overwrite=overwrite,
                resume=resume,
                progress=progress,
            )
        )
    progress.finish_all()

    if len(assets) + _METADATA_ASSET_COUNT > GITHUB_RELEASE_ASSET_LIMIT:
        raise ValueError(
            "Planned release exceeds GitHub's 1000 asset limit: "
            f"{len(assets)} data assets plus {_METADATA_ASSET_COUNT} metadata assets."
        )

    total_asset_size = sum(int(asset.get("size_bytes") or 0) for asset in assets)
    manifest = {
        "release_schema_version": DATA_RELEASE_SCHEMA_VERSION,
        "kind": DATA_RELEASE_KIND,
        "created_at_utc": _now_utc(),
        "label": label,
        "notes": notes or [],
        "dry_run": bool(dry_run),
        "max_asset_size_bytes": int(max_asset_size_bytes),
        "github_release_asset_limit": GITHUB_RELEASE_ASSET_LIMIT,
        "packaging": {
            "tar_compression": "mixed" if raw_cache_compression == "zstd" else "none",
            "tar_compression_by_role": {
                "raw_cache": raw_cache_compression,
                "factor_store": "none",
            },
            "raw_cache_compression": raw_cache_compression,
            "raw_cache_compression_level": (
                int(raw_cache_compression_level) if raw_cache_compression == "zstd" else None
            ),
            "raw_cache_zstd_window_log": (
                DEFAULT_RAW_CACHE_ZSTD_WINDOW_LOG if raw_cache_compression == "zstd" else None
            ),
            "oversized_file_strategy": "binary_split_parts",
            "resume": bool(resume),
        },
        "inputs": {
            "panel": str(panel_path) if panel_path is not None else None,
            "raw_cache": str(raw_cache_path) if raw_cache_path is not None else None,
            "factor_store": str(factor_store_path) if factor_store_path is not None else None,
        },
        "output": {
            "path": str(output_path),
            "space_check": space_check,
        },
        "panel": _panel_summary(panel_path) if panel_path is not None else None,
        "source_summary": {
            "panel_files": len(panel_sources),
            "raw_cache_files": len(raw_cache_sources),
            "factor_store_files": len(factor_store_sources),
        },
        "asset_summary": {
            "asset_count": len(assets),
            "metadata_asset_count": _METADATA_ASSET_COUNT,
            "total_upload_asset_count": len(assets) + _METADATA_ASSET_COUNT,
            "total_asset_size_bytes": total_asset_size,
        },
        "assets": assets,
        "environment": {
            "cwd": str(Path.cwd()),
            "git": _git_metadata(Path.cwd()),
        },
    }

    if dry_run:
        return DataReleaseResult(
            manifest_path=None,
            checksums_path=None,
            readme_path=None,
            upload_paths=tuple(Path(asset["path"]) for asset in assets),
            manifest=manifest,
        )

    manifest_path = output_path / "manifest.json"
    readme_path = output_path / "README.md"
    checksums_path = output_path / "sha256sums.txt"
    metadata_overwrite = overwrite or resume
    _ensure_can_write(manifest_path, overwrite=metadata_overwrite)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_readme(readme_path, manifest, overwrite=metadata_overwrite)

    checksum_entries = [
        *assets,
        {
            "relative_path": manifest_path.relative_to(output_path).as_posix(),
            "sha256": file_metadata(manifest_path)["sha256"],
        },
        {
            "relative_path": readme_path.relative_to(output_path).as_posix(),
            "sha256": file_metadata(readme_path)["sha256"],
        },
    ]
    _write_checksums(checksums_path, checksum_entries, overwrite=metadata_overwrite)

    upload_paths = [
        *(Path(asset["path"]) for asset in assets),
        manifest_path,
        checksums_path,
        readme_path,
    ]
    return DataReleaseResult(
        manifest_path=manifest_path,
        checksums_path=checksums_path,
        readme_path=readme_path,
        upload_paths=tuple(upload_paths),
        manifest=manifest,
    )


def build_github_release_upload_command(
    *,
    repo: str,
    tag: str,
    asset_paths: list[str | Path],
    clobber: bool = False,
) -> list[str]:
    command = ["gh", "release", "upload", tag, *(str(path) for path in asset_paths), "--repo", repo]
    if clobber:
        command.append("--clobber")
    return command


def upload_github_release_assets(
    *,
    repo: str,
    tag: str,
    asset_paths: list[str | Path],
    create_release: bool = False,
    release_title: str | None = None,
    notes_file: str | Path | None = None,
    clobber: bool = False,
) -> None:
    if create_release:
        create_command = ["gh", "release", "create", tag, "--repo", repo]
        if release_title:
            create_command.extend(["--title", release_title])
        if notes_file:
            create_command.extend(["--notes-file", str(notes_file)])
        subprocess.run(create_command, check=True)
    subprocess.run(
        build_github_release_upload_command(
            repo=repo,
            tag=tag,
            asset_paths=asset_paths,
            clobber=clobber,
        ),
        check=True,
    )
