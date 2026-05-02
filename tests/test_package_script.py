from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SCRIPT = PROJECT_ROOT / "project_tools" / "package.sh"


def _copy_package_script(repo: Path) -> Path:
    project_tools = repo / "project_tools"
    project_tools.mkdir(parents=True)
    target = project_tools / "package.sh"
    shutil.copy2(PACKAGE_SCRIPT, target)
    return target


def test_package_script_writes_archive_to_requested_out_dir(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    script = _copy_package_script(repo)
    (repo / "README.md").write_text("test repository\n", encoding="utf-8")
    (tmp_path / "parent-marker.txt").write_text("outside repository\n", encoding="utf-8")

    out_dir = tmp_path / "custom-output"
    work_dir = tmp_path / "work"
    caller_dir = tmp_path / "caller"
    caller_dir.mkdir()

    result = subprocess.run(
        [
            "bash",
            str(script),
            "--name",
            "sample",
            "--out-dir",
            str(out_dir),
            "--work-dir",
            str(work_dir),
            "--no-default-excludes",
        ],
        cwd=caller_dir,
        check=True,
        capture_output=True,
        text=True,
    )

    archives = sorted(out_dir.glob("sample_*.tar"))
    assert len(archives) == 1
    assert (out_dir / f"{archives[0].name}.sha256").is_file()
    assert f"Created: {archives[0]}" in result.stdout

    with tarfile.open(archives[0], "r:") as archive:
        names = set(archive.getnames())

    assert "./README.md" in names
    assert "./parent-marker.txt" not in names
    assert "./repo/README.md" not in names


def test_package_script_default_includes_runtime_outputs_for_data_transfer(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    script = _copy_package_script(repo)
    (repo / "README.md").write_text("test repository\n", encoding="utf-8")
    (repo / "data" / "panel").mkdir(parents=True)
    (repo / "data" / "panel" / "cn_daily.parquet").write_text("data\n", encoding="utf-8")
    (repo / "artifacts" / "run").mkdir(parents=True)
    (repo / "artifacts" / "run" / "metrics.json").write_text("{}\n", encoding="utf-8")
    (repo / "cache").mkdir()
    (repo / "cache" / "tmp.bin").write_text("cache\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    subprocess.run(
        [
            "bash",
            str(script),
            "--name",
            "source",
            "--out-dir",
            str(out_dir),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    [archive_path] = sorted(out_dir.glob("source_*.tar"))
    with tarfile.open(archive_path, "r:") as archive:
        names = set(archive.getnames())

    assert "./README.md" in names
    assert "./data/panel/cn_daily.parquet" in names
    assert "./artifacts/run/metrics.json" in names
    assert "./cache/tmp.bin" in names


def test_package_script_source_only_excludes_runtime_outputs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    script = _copy_package_script(repo)
    (repo / "README.md").write_text("test repository\n", encoding="utf-8")
    (repo / "data" / "panel").mkdir(parents=True)
    (repo / "data" / "panel" / "cn_daily.parquet").write_text("data\n", encoding="utf-8")
    (repo / "artifacts" / "run").mkdir(parents=True)
    (repo / "artifacts" / "run" / "metrics.json").write_text("{}\n", encoding="utf-8")
    (repo / "cache").mkdir()
    (repo / "cache" / "tmp.bin").write_text("cache\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    subprocess.run(
        [
            "bash",
            str(script),
            "--name",
            "source-only",
            "--out-dir",
            str(out_dir),
            "--source-only",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    [archive_path] = sorted(out_dir.glob("source-only_*.tar"))
    with tarfile.open(archive_path, "r:") as archive:
        names = set(archive.getnames())

    assert "./README.md" in names
    assert "./data/panel/cn_daily.parquet" not in names
    assert "./artifacts/run/metrics.json" not in names
    assert "./cache/tmp.bin" not in names


def test_package_script_can_write_tar_gz_when_requested(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    script = _copy_package_script(repo)
    (repo / "README.md").write_text("test repository\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    subprocess.run(
        [
            "bash",
            str(script),
            "--name",
            "source",
            "--out-dir",
            str(out_dir),
            "--format",
            "tar.gz",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    [archive_path] = sorted(out_dir.glob("source_*.tar.gz"))
    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())

    assert "./README.md" in names
