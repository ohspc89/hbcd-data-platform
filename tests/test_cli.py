import pytest
import duckdb
import subprocess
import sys

import hbcd_data_platform.pipeline as pipeline_module


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
            str(raw_path),
            "--db-path",
            str(db_path),
        ],
        capture_output=True,
        text=True,
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
            str(raw_path),
        ],
        capture_output=True,
        text=True,
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

    run_cli("ingest", "--raw-path", str(raw_path), "--db-path", str(db_path))
    run_cli("validate", "--db-path", str(db_path))

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
        pipeline_module.run_pipeline(raw_path, db_path)

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
        pipeline_module.run_pipeline(raw_path, db_path)

    with pytest.raises(duckdb.ConnectionException):
        captured_connections[0].execute("SELECT 1")

