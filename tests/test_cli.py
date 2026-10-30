import subprocess
import sys

import duckdb
import pytest

from conftest import make_synthetic_imu_parquet
import hbcd_data_platform.pipeline as pipeline_module
from hbcd_data_platform.config import PipelineConfig
from hbcd_data_platform.load_manifest import load_manifest


@pytest.fixture
def test_paths(tmp_path):
    raw_path = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"
    if not raw_path.is_dir():
        raw_path.mkdir()

    return raw_path, db_path


def test_cli_ingest_creates_manifest(test_paths):
    raw_path, db_path = test_paths

    sub1 = "sub-3911203980"
    (raw_path / sub1).mkdir()

    synthetic_file = raw_path / sub1 / f"{sub1}_sessions.tsv"
    synthetic_file.write_text(
        "session_id\tsite\tage\tage_adjusted\thead_size\nses-V02\thbcdsite33\t0.291\t14\t54\n"
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hbcd_data_platform.cli",
            "ingest",
            "--raw-path",
            raw_path,
            "--db-path",
            db_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    con = duckdb.connect(db_path)

    try:
        assert result.returncode == 0, result.stderr
        assert db_path.exists()
        assert con.sql("SELECT COUNT(*) FROM file_manifest").fetchone()[0] == 1
    finally:
        con.close()


def test_cli_ingest_requires_db_path(test_paths):
    raw_path, _ = test_paths

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hbcd_data_platform.cli",
            "ingest",
            "--raw-path",
            raw_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2, result.stderr
    assert "--db-path" in result.stderr


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "hbcd_data_platform.cli", *args],
        capture_output=True,
        text=True,
        check=True,
    )


def make_synthetic_sessions_tsv(raw_path, sub=None):

    if sub is None:
        sub = "sub-4122308196"

    (raw_path / sub).mkdir()
    synthetic_file = raw_path / sub / f"{sub}_sessions.tsv"
    synthetic_file.write_text(
        "session_id\tsite\tage\tage_adjusted\thead_size\nses-V02\thbcdsite33\t0.291\t14\t54\n"
    )


def test_cli_ingest_then_validate(test_paths):
    raw_path, db_path = test_paths

    make_synthetic_sessions_tsv(raw_path)

    run_cli("ingest", "--raw-path", raw_path, "--db-path", db_path)
    run_cli("validate", "--db-path", db_path)

    con = duckdb.connect(db_path)
    try:
        results_after_first = con.sql(
            "SELECT rule, status FROM validation_results ORDER BY rule, status;"
        ).fetchall()
        count_after_first = len(results_after_first)
        assert all(status == "PASS" for rule, status in results_after_first)
        assert count_after_first == 1
    finally:
        con.close()

    run_cli("validate", "--db-path", str(db_path))

    con = duckdb.connect(db_path)
    try:
        results_after_second = con.sql(
            "SELECT rule, status FROM validation_results ORDER BY rule, status;"
        ).fetchall()
        count_after_second = len(results_after_second)
        assert results_after_first == results_after_second
        assert count_after_second == 1
    finally:
        con.close()


def test_cli_run_pipeline(test_paths):
    raw_path, db_path = test_paths

    make_synthetic_sessions_tsv(raw_path, "sub-3810229374")

    run_cli("run", "--raw-path", str(raw_path), "--db-path", str(db_path))

    con = duckdb.connect(db_path)
    try:
        row_file_manifest = con.sql("SELECT COUNT(*) FROM file_manifest;").fetchone()[0]
        assert row_file_manifest == 1
        validation_results = con.sql(
            "SELECT rule, status FROM validation_results ORDER BY rule, status;"
        ).fetchall()
        assert len(validation_results) == 1
        assert validation_results[0][1] == "PASS"
    finally:
        con.close()


def test_pipeline_stops_when_ingest_fails(monkeypatch, test_paths):
    raw_path, db_path = test_paths

    def fake_load_manifest(raw_path, db_path):
        raise RuntimeError("Simulated load failure")

    monkeypatch.setattr(
        pipeline_module,
        "load_manifest",
        fake_load_manifest,
    )

    # If ingestion fails, no validation follows?
    validation_called = False

    def fake_save_validation_results(con):
        nonlocal validation_called
        validation_called = True

    monkeypatch.setattr(
        pipeline_module,
        "save_validation_results",
        fake_save_validation_results,
    )

    with pytest.raises(RuntimeError, match="Simulated load failure"):
        pipeline_module.run_pipeline(PipelineConfig(raw_path=raw_path, db_path=db_path))

    assert validation_called is False
    assert not db_path.exists()


def test_pipeline_stops_when_validation_fails(monkeypatch, test_paths):

    raw_path, db_path = test_paths
    make_synthetic_sessions_tsv(raw_path)

    captured_connections = []

    def fake_save_validation_results(con):
        captured_connections.append(con)
        raise RuntimeError("Simulated validation failure")

    monkeypatch.setattr(
        pipeline_module,
        "save_validation_results",
        fake_save_validation_results,
    )

    with pytest.raises(RuntimeError, match="Simulated validation failure"):
        pipeline_module.run_pipeline(PipelineConfig(raw_path=raw_path, db_path=db_path))

    with pytest.raises(duckdb.ConnectionException):
        captured_connections[0].execute("SELECT 1")


def test_ingest_fails_when_raw_path_does_not_exist(tmp_path):
    raw_path = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hbcd_data_platform.cli",
            "ingest",
            "--raw-path",
            raw_path,
            "--db-path",
            db_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, result.stderr
    assert not db_path.exists()
    assert str(raw_path) in result.stderr


def test_ingest_fails_when_raw_path_is_not_a_directory(tmp_path):
    raw_path = tmp_path / "raw_file.txt"
    db_path = tmp_path / "test.duckdb"

    raw_path.write_text("synthetic file", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hbcd_data_platform.cli",
            "ingest",
            "--raw-path",
            raw_path,
            "--db-path",
            db_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, result.stderr
    assert not db_path.exists()
    assert str(raw_path) in result.stderr


def test_ingest_fails_when_db_path_is_relative_to_raw_path(tmp_path):
    raw_path = tmp_path / "rawdata"
    raw_path.mkdir()
    db_path = raw_path / "test.duckdb"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hbcd_data_platform.cli",
            "ingest",
            "--raw-path",
            raw_path,
            "--db-path",
            db_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, result.stderr
    assert not db_path.exists()
    assert str(db_path.resolve()) in result.stderr


def test_process_imu_raises_error_when_no_db_file_exists(test_paths):
    raw_path, db_path = test_paths

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hbcd_data_platform.cli",
            "process-imu",
            "--raw-path",
            raw_path,
            "--db-path",
            db_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    assert "Database file not found" in result.stderr


def test_process_imu_raises_error_when_no_file_manifest_exists(test_paths):
    raw_path, db_path = test_paths

    con = duckdb.connect(db_path)
    con.close()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hbcd_data_platform.cli",
            "process-imu",
            "--raw-path",
            raw_path,
            "--db-path",
            db_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    assert "The table 'file_manifest' is not found" in result.stderr


def test_process_imu_runs_when_proper_manifest_exists(test_paths):
    raw_path, db_path = test_paths

    filepath = (
        raw_path
        / "sub-2938190832_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet"
    )

    make_synthetic_imu_parquet(filepath)

    load_manifest(raw_path, db_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hbcd_data_platform.cli",
            "process-imu",
            "--raw-path",
            raw_path,
            "--db-path",
            db_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    with duckdb.connect(db_path) as con:
        n_windows = con.execute(
            "SELECT COUNT(*) FROM imu_window_summary"
        ).fetchone()[0]

    # 4 rows
    assert n_windows == 4


def test_process_imu_returns_one_when_processing_fails(test_paths):
    raw_path, db_path = test_paths

    for task in ["LeftLegMovement", "RightLegMovement"]:
        make_synthetic_imu_parquet(
            raw_path / f"sub-2938190832_ses-V02_task-{task}_tracksys-imu_acq-primary_motion.parquet")

    load_manifest(raw_path, db_path)

    # Delete one file
    (raw_path / "sub-2938190832_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet").unlink()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hbcd_data_platform.cli",
            "process-imu",
            "--raw-path",
            raw_path,
            "--db-path",
            db_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    assert "Processed" in result.stdout
    assert "Processed : 1" in result.stdout
    assert "Failed" in result.stdout
    assert "Failed    : 1" in result.stdout

    with duckdb.connect(db_path) as con:
        processed_files = con.execute(
            """
            SELECT f.task
            FROM imu_processing_status AS s
            JOIN file_manifest f ON s.file_id = f.file_id
            """
        ).fetchall()

        assert processed_files == [("RightLegMovement",)]


def test_repeated_process_imu_skips_unchanged_files(test_paths):
    raw_path, db_path = test_paths

    for task in ["LeftLegMovement", "RightLegMovement"]:
        make_synthetic_imu_parquet(
            raw_path / f"sub-2938190832_ses-V02_task-{task}_tracksys-imu_acq-primary_motion.parquet")

    load_manifest(raw_path, db_path)

    first_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hbcd_data_platform.cli",
            "process-imu",
            "--raw-path",
            raw_path,
            "--db-path",
            db_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert first_result.returncode == 0, first_result.stderr
    assert "Processed : 2" in first_result.stdout
    assert "Skipped   : 0" in first_result.stdout

    second_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hbcd_data_platform.cli",
            "process-imu",
            "--raw-path",
            raw_path,
            "--db-path",
            db_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert second_result.returncode == 0, second_result.stderr
    assert "Processed : 0" in second_result.stdout
    assert "Skipped   : 2" in second_result.stdout
