from pathlib import Path

import duckdb
import pytest

from conftest import make_synthetic_imu_parquet
from hbcd_data_platform.load_manifest import load_manifest
import hbcd_data_platform.orchestration as orchestration_module
from hbcd_data_platform.orchestration import process_imu_file


def test_repeated_orchestration_yields_no_duplicates(tmp_path):
    rawpath = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"

    motion_path = rawpath / "sub-7236112352/ses-V02/motion"
    motion_path.mkdir(parents=True, exist_ok=True)

    filename1 = (
        "sub-7236112352_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.parquet"
    )

    primary_path1 = motion_path / filename1

    # 200 rows (8 seconds = 200 / 25)
    make_synthetic_imu_parquet(primary_path1)

    load_manifest(rawpath, db_path)

    con = duckdb.connect(db_path)

    # Need to get an id.
    file_id = con.execute(
        """
        SELECT file_id
        FROM file_manifest
        WHERE filename = ?;
        """,
        [filename1],
    ).fetchone()[0]

    try:
        # The number of windows is 4
        process_imu_file(con, file_id, rawpath, 2.0)

        assert (
            con.execute(
                "SELECT COUNT(*) FROM imu_window_summary WHERE file_id = ?", [file_id]
            ).fetchone()[0]
            == 4
        )

        # Run the function again, and still no duplicates generated
        process_imu_file(con, file_id, rawpath, 2.0)

        assert (
            con.execute(
                "SELECT COUNT(*) FROM imu_window_summary WHERE file_id = ?", [file_id]
            ).fetchone()[0]
            == 4
        )
    finally:
        con.close()


def test_failed_calculation_saves_original_db_data(tmp_path, monkeypatch):
    rawpath = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"

    motion_path = rawpath / "sub-7236112352/ses-V02/motion"
    motion_path.mkdir(parents=True, exist_ok=True)

    filename1 = (
        "sub-7236112352_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.parquet"
    )

    primary_path1 = motion_path / filename1

    # 200 rows (8 seconds = 200 / 25)
    make_synthetic_imu_parquet(primary_path1)

    load_manifest(rawpath, db_path)

    con = duckdb.connect(db_path)

    # Need to get an id.
    file_id = con.execute(
        """
        SELECT file_id
        FROM file_manifest
        WHERE filename = ?;
        """,
        [filename1],
    ).fetchone()[0]

    def fake_summarize(*args, **kwargs):
        raise RuntimeError("Simulated calculation failure")

    try:
        # The number of windows is 4
        process_imu_file(con, file_id, rawpath, 2.0)

        window_summary = con.execute(
            """
            SELECT *
            FROM imu_window_summary
            WHERE file_id = ?
            ORDER BY window_index
            """,
            [file_id],
        ).fetchall()
        assert len(window_summary) == 4

        monkeypatch.setattr(
            orchestration_module.imu_module, "summarize_imu_windows", fake_summarize
        )
        # Run the function again, and still no duplicates generated
        with pytest.raises(RuntimeError, match="Simulated calculation failure"):
            process_imu_file(con, file_id, rawpath, 2.0)

        whether_saved = con.execute(
            """
            SELECT *
            FROM imu_window_summary
            WHERE file_id = ?
            ORDER BY window_index
            """,
            [file_id],
        ).fetchall()

        assert window_summary == whether_saved
    finally:
        con.close()


def test_failed_replacement_saves_original_db_data(tmp_path):
    rawpath = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"

    motion_path = rawpath / "sub-7236112352/ses-V02/motion"
    motion_path.mkdir(parents=True, exist_ok=True)

    filename1 = (
        "sub-7236112352_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.parquet"
    )

    primary_path1 = motion_path / filename1

    # 200 rows (8 seconds = 200 / 25)
    make_synthetic_imu_parquet(primary_path1)

    load_manifest(rawpath, db_path)

    con = duckdb.connect(db_path)

    # Need to get an id.
    file_id = con.execute(
        """
        SELECT file_id
        FROM file_manifest
        WHERE filename = ?;
        """,
        [filename1],
    ).fetchone()[0]

    try:
        # The number of windows is 4
        process_imu_file(con, file_id, rawpath, 2.0)

        result = con.execute(
            """
            SELECT *
            FROM imu_window_summary
            WHERE file_id = ?
            ORDER BY window_index
            """,
            [file_id],
        )

        columns = [col[0] for col in result.description]
        summaries = result.fetchall()
        assert len(summaries) == 4

        invalid_summaries = [dict(zip(columns, row)) for row in summaries]
        invalid_summaries[0]["sample_count"] = None

        with pytest.raises(duckdb.ConstraintException):
            orchestration_module.imu_module.replace_imu_window_summaries(
                con, file_id, invalid_summaries
            )

        rollbacked = con.execute(
            """
            SELECT *
            FROM imu_window_summary
            WHERE file_id = ?
            ORDER BY window_index
            """,
            [file_id],
        ).fetchall()

        assert summaries == rollbacked
    finally:
        con.close()
