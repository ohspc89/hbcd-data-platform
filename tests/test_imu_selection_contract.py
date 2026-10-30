"""Regression test for HBCD IMU file-selection policy.

Copy this file into the repository's tests/ directory and run:
    uv run pytest -q tests/test_imu_selection_contract.py

This test is expected to fail against the 2026-10-28 GitHub main branch:
run_imu_processing currently does not filter acquisition='primary'.
"""

import duckdb

from conftest import make_synthetic_imu_parquet
from hbcd_data_platform.load_manifest import load_manifest
from hbcd_data_platform.orchestration import run_imu_processing


def test_imu_processing_only_selects_primary_recordings(tmp_path):
    raw_path = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"
    motion_dir = raw_path / "sub-7236112352" / "ses-V02" / "motion"
    motion_dir.mkdir(parents=True)

    # Both files have valid sensor schemas; acquisition is the only difference.
    for acquisition in ("primary", "calibration"):
        filename = (
            "sub-7236112352_ses-V02_task-LeftLegMovement_"
            f"tracksys-imu_acq-{acquisition}_motion.parquet"
        )
        make_synthetic_imu_parquet(motion_dir / filename)

    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)
    try:
        run_imu_processing(con, raw_path, window_seconds=2.0)

        processed_acquisitions = {
            row[0]
            for row in con.execute(
                """
                SELECT f.acquisition
                FROM imu_processing_status AS s
                JOIN file_manifest AS f ON f.file_id = s.file_id
                """
            ).fetchall()
        }
        assert processed_acquisitions == {"primary"}

        summary_acquisitions = {
            row[0]
            for row in con.execute(
                """
                SELECT DISTINCT f.acquisition
                FROM imu_window_summary AS w
                JOIN file_manifest AS f ON f.file_id = w.file_id
                """
            ).fetchall()
        }
        assert summary_acquisitions == {"primary"}
    finally:
        con.close()


def test_imu_processing_only_present_files(tmp_path):
    raw_path = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"
    motion_dir = raw_path / "sub-7236112352" / "ses-V02" / "motion"
    motion_dir.mkdir(parents=True)

    for movement in ("LeftLegMovement", "RightLegMovement"):
        filename = (
            f"sub-7236112352_ses-V02_task-{movement}_"
            "tracksys-imu_acq-primary_motion.parquet"
        )
        make_synthetic_imu_parquet(motion_dir / filename)

    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)
    try:
        con.execute(
            """
            UPDATE file_manifest AS f
            SET is_present = FALSE
            WHERE task = 'RightLegMovement'
            """
        )
        run_imu_processing(con, raw_path, window_seconds=2.0)

        filename_in_table = (
            "sub-7236112352_ses-V02_task-LeftLegMovement_"
            "tracksys-imu_acq-primary_motion.parquet"
        )

        processed_filenames = {
            row[0]
            for row in con.execute(
                """
                SELECT f.filename
                FROM imu_processing_status AS s
                JOIN file_manifest AS f ON f.file_id = s.file_id
                """
            ).fetchall()
        }
        assert processed_filenames == {filename_in_table}

        summary_filenames = {
            row[0]
            for row in con.execute(
                """
                SELECT DISTINCT f.filename
                FROM imu_window_summary AS w
                JOIN file_manifest AS f ON f.file_id = w.file_id
                """
            ).fetchall()
        }
        assert summary_filenames == {filename_in_table}
    finally:
        con.close()
