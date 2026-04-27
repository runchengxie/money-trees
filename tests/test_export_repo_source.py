from __future__ import annotations

from pathlib import Path

from project_tools.export_repo_source import (
    EXCLUDE_FILES,
    PROJECT_ROOT,
    get_archive_file_status,
    get_directory_exclude_reason,
)


def test_export_repo_source_includes_configs_directory() -> None:
    reason = get_directory_exclude_reason("configs", PROJECT_ROOT, PROJECT_ROOT)

    assert reason is None


def test_export_repo_source_includes_factor_catalog_csv() -> None:
    include, reason = get_archive_file_status(
        PROJECT_ROOT / "docs" / "factor_catalog.csv",
        set(EXCLUDE_FILES),
    )

    assert include is True
    assert reason == "repository text asset"


def test_export_repo_source_includes_factor_catalog_csv_under_custom_root(tmp_path: Path) -> None:
    catalog_path = tmp_path / "docs" / "factor_catalog.csv"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text("family,column\n", encoding="utf-8")

    include, reason = get_archive_file_status(catalog_path, set(EXCLUDE_FILES))

    assert include is True
    assert reason == "repository text asset"


def test_export_repo_source_still_excludes_runtime_data_directory(tmp_path: Path) -> None:
    reason = get_directory_exclude_reason("data", tmp_path, tmp_path)

    assert reason == "excluded root-only directory"
