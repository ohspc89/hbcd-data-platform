import dataclasses
from pathlib import Path

import pytest

from hbcd_data_platform.config import PipelineConfig, validate_pipeline_config


def test_config_stores_paths(tmp_path):
    """Verify that configuration preserves the supplied paths."""
    obj = PipelineConfig(
        raw_path=tmp_path / "rawdata", db_path=tmp_path / "hbcd.duckdb"
    )

    assert obj.raw_path == tmp_path / "rawdata"
    assert obj.db_path == tmp_path / "hbcd.duckdb"


def test_config_is_frozen(tmp_path):
    """Verify that configuration is frozen."""
    obj = PipelineConfig(
        raw_path=tmp_path / "rawdata",
        db_path=tmp_path / "hbcd.duckdb",
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        obj.raw_path = Path("rawdata")


def test_raw_path_is_an_existing_directory(tmp_path):
    raw_path = tmp_path / "rawdata"
    raw_path.mkdir()

    obj = PipelineConfig(raw_path=raw_path, db_path=tmp_path / "hbcd.duckdb")

    validate_pipeline_config(obj)


def test_raw_path_does_not_exist(tmp_path):
    raw_path = tmp_path / "does_not_exist"
    obj = PipelineConfig(raw_path=raw_path, db_path=tmp_path / "hbcd.duckdb")

    with pytest.raises(FileNotFoundError) as exc_info:
        validate_pipeline_config(obj)

    assert str(raw_path) in str(exc_info.value)


def test_raw_path_is_not_a_directory(tmp_path):
    raw_path = tmp_path / "sample.txt"
    raw_path.write_text("synthetic test data", encoding="utf-8")
    obj = PipelineConfig(raw_path=raw_path, db_path=tmp_path / "hbcd.duckdb")

    with pytest.raises(NotADirectoryError) as exc_info:
        validate_pipeline_config(obj)

    assert str(raw_path) in str(exc_info.value)


def test_db_path_inside_the_input_directory(tmp_path):
    raw_path = tmp_path
    db_path = tmp_path / "test.duckdb"
    obj = PipelineConfig(raw_path=raw_path, db_path=db_path)

    with pytest.raises(ValueError) as exc_info:
        validate_pipeline_config(obj)

    assert str(db_path.resolve()) in str(exc_info.value)
