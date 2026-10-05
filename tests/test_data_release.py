from __future__ import annotations

import json
import tarfile

import pandas as pd

from moneytree.cli.data_release import main
from moneytree.data import save_market_data
from moneytree.data_release import create_data_release, resolve_release_output_dir
from moneytree.factor_store import write_factor_store


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-04", "2021-01-05", "2021-01-05"]),
            "ticker": ["000001.SZ", "000001.SZ", "000002.SZ"],
            "open": [10.0, 10.2, 20.0],
            "high": [10.3, 10.5, 20.5],
            "low": [9.8, 10.0, 19.8],
            "close": [10.1, 10.4, 20.1],
            "volume": [1000.0, 1100.0, 2100.0],
            "vwap": [10.05, 10.3, 20.0],
            "next_period_return": [0.01, 0.02, 0.03],
            "benchmark_cum_ret": [1.0, 1.01, 1.01],
            "benchmark_next_period_return": [0.0, 0.0, 0.0],
            "hit_up_limit": [False, False, False],
            "hit_down_limit": [False, False, False],
            "is_suspended": [False, False, False],
            "is_st": [False, False, False],
            "alpha158_kmid": [0.1, 0.2, 0.3],
        }
    )


def test_create_data_release_writes_panel_factor_store_assets_and_metadata(tmp_path) -> None:
    panel_path = tmp_path / "panel.parquet"
    save_market_data(_panel().set_index(["date", "ticker"]), panel_path)
    store_dir = tmp_path / "store"
    write_factor_store(_panel(), store_dir, families=["alpha158"])

    result = create_data_release(
        panel=panel_path,
        factor_store=store_dir,
        output_dir=tmp_path / "release",
        max_asset_size_bytes=1024 * 1024,
        label="unit-test-release",
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["kind"] == "moneytree_data_release"
    assert manifest["label"] == "unit-test-release"
    assert manifest["panel"]["rows"] == 3
    assert manifest["asset_summary"]["asset_count"] == 2
    assert manifest["asset_summary"]["total_upload_asset_count"] == 5
    assert (tmp_path / "release" / "panel__panel.parquet").exists()
    assert (tmp_path / "release" / "factor_store_part001.tar").exists()
    assert "manifest.json" in result.checksums_path.read_text(encoding="utf-8")

    with tarfile.open(tmp_path / "release" / "factor_store_part001.tar", "r") as tar:
        names = set(tar.getnames())
    assert "factor_store/manifest.json" in names
    assert "factor_store/factors/alpha158.parquet" in names


def test_create_data_release_resumes_existing_complete_assets(tmp_path) -> None:
    panel_path = tmp_path / "panel.parquet"
    save_market_data(_panel().set_index(["date", "ticker"]), panel_path)
    store_dir = tmp_path / "store"
    write_factor_store(_panel(), store_dir, families=["alpha158"])
    output_dir = tmp_path / "release"

    create_data_release(
        panel=panel_path,
        factor_store=store_dir,
        output_dir=output_dir,
        max_asset_size_bytes=1024 * 1024,
    )
    result = create_data_release(
        panel=panel_path,
        factor_store=store_dir,
        output_dir=output_dir,
        max_asset_size_bytes=1024 * 1024,
    )

    assert {asset["resume_status"] for asset in result.manifest["assets"]} == {"reused"}


def test_create_data_release_splits_oversized_raw_cache_file(tmp_path) -> None:
    raw_cache = tmp_path / "raw"
    raw_cache.mkdir()
    payload = b"abcdefghijklmnopqrstuvwxyz"
    (raw_cache / "large.parquet").write_bytes(payload)

    result = create_data_release(
        raw_cache=raw_cache,
        output_dir=tmp_path / "release",
        max_asset_size_bytes=10,
    )

    assets = result.manifest["assets"]
    assert [asset["type"] for asset in assets] == ["split_part", "split_part", "split_part"]
    assert assets[0]["split"]["source_sha256"]
    restored = b"".join((tmp_path / "release" / asset["name"]).read_bytes() for asset in assets)
    assert restored == payload


def test_create_data_release_compresses_and_resumes_raw_cache_archive(tmp_path) -> None:
    import zstandard

    raw_cache = tmp_path / "raw"
    raw_cache.mkdir()
    payload = b"daily market cache row\n" * 4096
    (raw_cache / "daily.parquet").write_bytes(payload)
    store_dir = tmp_path / "store"
    write_factor_store(_panel(), store_dir, families=["alpha158"])
    output_dir = tmp_path / "release"

    result = create_data_release(
        raw_cache=raw_cache,
        factor_store=store_dir,
        output_dir=output_dir,
        raw_cache_compression="zstd",
        raw_cache_compression_level=19,
    )

    asset = next(item for item in result.manifest["assets"] if item["role"] == "raw_cache")
    assert asset["name"] == "raw_cache_zstd19_part001.tar.zst"
    assert asset["compression"] == "zstd"
    assert asset["compression_level"] == 19
    assert asset["window_log"] == 27
    factor_asset = next(
        item for item in result.manifest["assets"] if item["role"] == "factor_store"
    )
    assert factor_asset["name"] == "factor_store_part001.tar"
    assert factor_asset["compression"] == "none"
    assert result.manifest["release_schema_version"] == "1.1"
    assert result.manifest["packaging"]["tar_compression_by_role"] == {
        "raw_cache": "zstd",
        "factor_store": "none",
    }
    assert result.manifest["packaging"]["raw_cache_zstd_window_log"] == 27
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "zstd -d -c <asset>.tar.zst | tar -xf -" in readme
    with (output_dir / asset["name"]).open("rb") as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
            with tarfile.open(fileobj=reader, mode="r|") as archive:
                members = {
                    member.name: archive.extractfile(member).read()
                    for member in archive
                    if member.isfile() and member.name == "raw_cache/daily.parquet"
                }
                assert members["raw_cache/daily.parquet"] == payload

    resumed = create_data_release(
        raw_cache=raw_cache,
        output_dir=output_dir,
        raw_cache_compression="zstd",
        raw_cache_compression_level=19,
    )
    resumed_asset = next(
        item for item in resumed.manifest["assets"] if item["role"] == "raw_cache"
    )
    assert resumed_asset["resume_status"] == "reused"


def test_create_data_release_rebuilds_corrupt_compressed_raw_cache_archive(tmp_path) -> None:
    import zstandard

    raw_cache = tmp_path / "raw"
    raw_cache.mkdir()
    (raw_cache / "daily.parquet").write_bytes(b"daily market cache row\n" * 64)
    output_dir = tmp_path / "release"
    options = {
        "raw_cache": raw_cache,
        "output_dir": output_dir,
        "raw_cache_compression": "zstd",
    }

    first = create_data_release(**options)
    asset = next(item for item in first.manifest["assets"] if item["role"] == "raw_cache")
    archive_path = output_dir / asset["name"]
    archive_path.write_bytes(b"not a zstandard archive")

    rebuilt = create_data_release(**options)

    rebuilt_asset = next(item for item in rebuilt.manifest["assets"] if item["role"] == "raw_cache")
    assert rebuilt_asset["resume_status"] == "written"
    with archive_path.open("rb") as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
            with tarfile.open(fileobj=reader, mode="r|") as archive:
                members = {
                    member.name: archive.extractfile(member).read()
                    for member in archive
                    if member.isfile() and member.name == "raw_cache/daily.parquet"
                }
                assert members["raw_cache/daily.parquet"] == b"daily market cache row\n" * 64


def test_data_release_cli_accepts_raw_cache_compression_options(tmp_path, capsys) -> None:
    raw_cache = tmp_path / "raw"
    raw_cache.mkdir()
    (raw_cache / "daily.parquet").write_bytes(b"daily")

    exit_code = main(
        [
            "--raw-cache",
            str(raw_cache),
            "--output-dir",
            str(tmp_path / "release"),
            "--raw-cache-compression",
            "zstd",
            "--raw-cache-compression-level",
            "3",
            "--format",
            "json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["manifest"]["packaging"]["raw_cache_compression"] == "zstd"
    assert payload["manifest"]["packaging"]["raw_cache_compression_level"] == 3
    assert payload["manifest"]["packaging"]["raw_cache_zstd_window_log"] == 27


def test_data_release_cli_outputs_json_dry_run(tmp_path, capsys) -> None:
    raw_cache = tmp_path / "raw"
    raw_cache.mkdir()
    (raw_cache / "daily.parquet").write_bytes(b"daily")

    exit_code = main(
        [
            "--raw-cache",
            str(raw_cache),
            "--output-dir",
            str(tmp_path / "release"),
            "--dry-run",
            "--github-repo",
            "owner/repo",
            "--github-tag",
            "data-cn-test",
            "--format",
            "json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["manifest"]["dry_run"] is True
    assert payload["manifest_path"] is None
    assert payload["upload_command"][:3] == ["gh", "release", "upload"]
    assert not (tmp_path / "release").exists()


def test_data_release_cli_progress_outputs_stderr(tmp_path, capsys) -> None:
    raw_cache = tmp_path / "raw"
    raw_cache.mkdir()
    (raw_cache / "daily.parquet").write_bytes(b"daily")

    exit_code = main(
        [
            "--raw-cache",
            str(raw_cache),
            "--output-dir",
            str(tmp_path / "release"),
            "--progress",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[data-release]" in captured.err


def test_resolve_release_output_dir_supports_windows_drive_paths() -> None:
    from moneytree.data_release import _is_wsl

    if _is_wsl():
        assert resolve_release_output_dir("D:/money-tree/releases").as_posix() == (
            "/mnt/d/money-tree/releases"
        )
        assert resolve_release_output_dir(r"E:\release assets\cn").as_posix() == (
            "/mnt/e/release assets/cn"
        )
    else:
        assert resolve_release_output_dir("D:/money-tree/releases").as_posix() == (
            "D:/money-tree/releases"
        )
        assert resolve_release_output_dir(r"E:\release assets\cn").as_posix() == (
            "E:/release assets/cn"
        )


def test_data_release_refuses_env_files(tmp_path, capsys) -> None:
    raw_cache = tmp_path / "raw"
    raw_cache.mkdir()
    (raw_cache / ".env").write_text("TOKEN=secret\n", encoding="utf-8")

    exit_code = main(
        [
            "--raw-cache",
            str(raw_cache),
            "--output-dir",
            str(tmp_path / "release"),
        ]
    )

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "Refusing to package sensitive file path" in err
