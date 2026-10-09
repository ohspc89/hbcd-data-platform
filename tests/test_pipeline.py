import pytest
import logging

import hbcd_data_platform.pipeline as pipeline_module


@pytest.fixture
def test_paths(tmp_path):
    raw_path = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"
    if not raw_path.is_dir():
        raw_path.mkdir()

    return raw_path, db_path


def make_synthetic_sessions_tsv(raw_path, sub=None):

    if sub is None:
        sub = "sub-4122308196"

    (raw_path / sub).mkdir()
    synthetic_file = raw_path / sub / f"{sub}_sessions.tsv"
    synthetic_file.write_text(
        "session_id\tsite\tage\tage_adjusted\thead_size\nses-V02\thbcdsite33\t0.291\t14\t54\n"
    )


def test_pipeline_logs_success(caplog, test_paths):
    raw_path, db_path = test_paths
    make_synthetic_sessions_tsv(raw_path)

    with caplog.at_level(
        logging.INFO,
        logger="hbcd_data_platform.pipeline",
    ):
        pipeline_module.run_pipeline(raw_path, db_path)

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "hbcd_data_platform.pipeline"
    ]

    assert messages == [
        "Pipeline started",
        "Ingestion completed",
        "Validation completed",
        "Pipeline finished",
    ]


def test_pipeline_logs_error(caplog, monkeypatch, test_paths):
    raw_path, db_path = test_paths
    make_synthetic_sessions_tsv(raw_path)

    def fake_save_validation_results(con):
        raise RuntimeError("Simulated validation failure")

    monkeypatch.setattr(
        pipeline_module,
        "save_validation_results",
        fake_save_validation_results,
    )

    with (
        caplog.at_level(
            logging.ERROR,
            logger="hbcd_data_platform.pipeline",
        ),
        pytest.raises(RuntimeError, match="Simulated validation failure"),
    ):
        pipeline_module.run_pipeline(raw_path, db_path)

    error_records = [
        record
        for record in caplog.records
        if record.name == "hbcd_data_platform.pipeline"
    ]

    assert len(error_records) == 1
    assert error_records[0].getMessage() == "Validation failed"
    assert error_records[0].exc_info is not None
