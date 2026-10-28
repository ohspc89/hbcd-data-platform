import os
import shutil

import duckdb
import pytest
from conftest import make_synthetic_imu_parquet
from unittest.mock import Mock

import hbcd_data_platform.orchestration as orchestration_module
from hbcd_data_platform.imu import (
    create_imu_processing_status_table,
    create_imu_window_summary_table,
    summarize_imu_windows,
)
from hbcd_data_platform.load_manifest import load_manifest
from hbcd_data_platform.orchestration import process_imu_file, run_imu_processing


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
        create_imu_window_summary_table(con)
        create_imu_processing_status_table(con)
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
        create_imu_window_summary_table(con)
        create_imu_processing_status_table(con)
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
        create_imu_window_summary_table(con)
        create_imu_processing_status_table(con)
        # The number of windows is 4
        window_seconds = 2.0
        process_imu_file(con, file_id, rawpath, window_seconds)

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
                con, file_id, invalid_summaries, window_seconds
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


def test_run_imu_processing_handles_multiple_new_files(tmp_path):
    rawpath = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"

    motion_path = rawpath / "sub-7236112352/ses-V02/motion"
    motion_path.mkdir(parents=True, exist_ok=True)

    filename1 = (
        "sub-7236112352_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.parquet"
    )
    filename2 = (
        "sub-7236112352_ses-V02_task-RightLegMovement"
        "_tracksys-imu_acq-primary_motion.parquet"
    )

    all_new_files = [filename1, filename2]

    primary_path1 = motion_path / filename1
    primary_path2 = motion_path / filename2

    # 200 rows (8 seconds = 200 / 25)
    make_synthetic_imu_parquet(primary_path1)
    make_synthetic_imu_parquet(primary_path2)

    load_manifest(rawpath, db_path)

    con = duckdb.connect(db_path)
    try:
        run_imu_processing(con, rawpath)
        for ind_filename in all_new_files:
            file_id_n = con.execute(
                """
                SELECT file_id
                FROM file_manifest
                WHERE filename = ?;
                """,
                [ind_filename],
            ).fetchone()[0]
            assert (
                con.execute(
                    "SELECT COUNT(*) FROM imu_window_summary WHERE file_id = ?",
                    [file_id_n],
                ).fetchone()[0]
                == 4
            )

        assert (
            con.execute("SELECT COUNT(*) FROM imu_processing_status").fetchone()[0] == 2
        )
    finally:
        con.close()


def test_run_imu_processing_doesnt_reprocess_unchanged_files(tmp_path, monkeypatch):
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
    try:
        run_imu_processing(con, rawpath)
        processed_at_before = con.execute(
            "SELECT processed_at FROM imu_processing_status"
        ).fetchone()[0]

        # run one more time
        run_imu_processing(con, rawpath)
        processed_at_after = con.execute(
            "SELECT processed_at FROM imu_processing_status"
        ).fetchone()[0]

        assert processed_at_before == processed_at_after

        # You can check calls
        calls = []

        def record_call(*args, **kwargs):
            calls.append(args)

        monkeypatch.setattr(
            "hbcd_data_platform.orchestration.process_imu_file",
            record_call,
        )
        run_imu_processing(con, rawpath)

        assert calls == []

    finally:
        con.close()


def test_run_imu_processing_reprocesses_when_filesize_changes(tmp_path, monkeypatch):
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
    try:
        run_imu_processing(con, rawpath)
        # Change the filesize in file_manifest
        con.execute(
            """
            UPDATE file_manifest
            SET size_bytes=size_bytes+1
            WHERE filename=?
            """,
            [filename1],
        )

        calls = []

        def record_call(*args, **kwargs):
            calls.append(args)

        monkeypatch.setattr(
            "hbcd_data_platform.orchestration.process_imu_file",
            record_call,
        )

        run_imu_processing(con, rawpath)

        file_id = con.execute(
            "SELECT file_id FROM file_manifest WHERE filename=?", [filename1]
        ).fetchone()[0]

        assert len(calls) == 1
        assert calls[0][1] == file_id

    finally:
        con.close()


def test_run_imu_processing_continues_even_when_a_file_fails(
    tmp_path, monkeypatch, caplog
):
    rawpath = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"

    motion_path = rawpath / "sub-7236112352/ses-V02/motion"
    motion_path.mkdir(parents=True, exist_ok=True)

    filename1 = (
        "sub-7236112352_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.parquet"
    )
    filename2 = (
        "sub-7236112352_ses-V02_task-RightLegMovement"
        "_tracksys-imu_acq-primary_motion.parquet"
    )

    primary_path1 = motion_path / filename1
    primary_path2 = motion_path / filename2

    # 200 rows (8 seconds = 200 / 25)
    make_synthetic_imu_parquet(primary_path1)
    make_synthetic_imu_parquet(primary_path2)

    load_manifest(rawpath, db_path)

    original_summarize = orchestration_module.imu_module.summarize_imu_windows

    def summarize_with_failure(path, window_seconds=2.0):
        if "LeftLegMovement" in str(path):
            raise RuntimeError("Simulated processing failure")

        return original_summarize(path, window_seconds=window_seconds)

    monkeypatch.setattr(
        orchestration_module.imu_module, "summarize_imu_windows", summarize_with_failure
    )

    con = duckdb.connect(db_path)
    try:
        run_imu_processing(con, rawpath)
        failed_file_id = con.execute(
            """
            SELECT file_id
            FROM file_manifest
            WHERE filename=?
            """,
            [filename1],
        ).fetchone()[0]
        assert (
            con.execute(
                "SELECT COUNT(*) FROM imu_window_summary WHERE file_id = ?",
                [failed_file_id],
            ).fetchone()[0]
            == 0
        )
        # no entry for failed_file_id
        assert (
            con.execute(
                "SELECT COUNT(*) FROM imu_processing_status WHERE file_id = ?",
                [failed_file_id],
            ).fetchone()[0]
            == 0
        )
        succeeded_file_id = con.execute(
            """
            SELECT file_id
            FROM file_manifest
            WHERE filename=?
            """,
            [filename2],
        ).fetchone()[0]
        assert (
            con.execute(
                "SELECT COUNT(*) FROM imu_window_summary WHERE file_id = ?",
                [succeeded_file_id],
            ).fetchone()[0]
            == 4
        )
        assert (
            con.execute(
                "SELECT COUNT(*) FROM imu_processing_status WHERE file_id = ?",
                [succeeded_file_id],
            ).fetchone()[0]
            == 1
        )

        assert "Simulated processing failure" in caplog.text

    finally:
        con.close()


def test_run_imu_processing_runs_with_a_zero_window(tmp_path, monkeypatch):
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

    monkeypatch.setattr(
        orchestration_module.imu_module,
        "summarize_imu_windows",
        lambda *args, **kwargs: [],
    )
    con = duckdb.connect(db_path)
    try:
        run_imu_processing(con, rawpath)
        passed_file_id = con.execute(
            """
            SELECT file_id
            FROM file_manifest
            WHERE filename=?
            """,
            [filename1],
        ).fetchone()[0]
        assert (
            con.execute(
                "SELECT COUNT(*) FROM imu_window_summary WHERE file_id = ?",
                [passed_file_id],
            ).fetchone()[0]
            == 0
        )
        assert (
            con.execute(
                "SELECT COUNT(*) FROM imu_processing_status WHERE file_id = ?",
                [passed_file_id],
            ).fetchone()[0]
            == 1
        )

        calls = []

        def record_call(*args, **kwargs):
            calls.append(args)

        monkeypatch.setattr(
            "hbcd_data_platform.orchestration.process_imu_file",
            record_call,
        )
        # Run one more time - no re-processing
        run_imu_processing(con, rawpath)

        assert calls == []
    finally:
        con.close()


def test_removed_file_preserves_previous_results(tmp_path, monkeypatch):
    rawpath = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"

    motion_path = rawpath / "sub-7236112352/ses-V02/motion"
    motion_path.mkdir(parents=True, exist_ok=True)

    filename1 = (
        "sub-7236112352_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.parquet"
    )
    filename2 = (
        "sub-7236112352_ses-V02_task-RightLegMovement"
        "_tracksys-imu_acq-primary_motion.parquet"
    )

    primary_path1 = motion_path / filename1
    primary_path2 = motion_path / filename2

    # 200 rows (8 seconds = 200 / 25)
    make_synthetic_imu_parquet(primary_path1)
    make_synthetic_imu_parquet(primary_path2)

    load_manifest(rawpath, db_path)

    con = duckdb.connect(db_path)

    # Get the file_id of filename1
    file_id_of_interest = con.execute(
        """
        SELECT file_id
        FROM file_manifest
        WHERE filename = $filename1;
        """,
        {"filename1": filename1},
    ).fetchone()[0]

    try:
        run_imu_processing(con, rawpath)
        summaries_before = con.execute(
            """
            SELECT *
            FROM imu_window_summary
            WHERE file_id = ?
            ORDER BY window_index
            """,
            [file_id_of_interest],
        ).fetchall()
        status_before = con.execute(
            """
            SELECT *
            FROM imu_processing_status
            WHERE file_id = ?
            """,
            [file_id_of_interest],
        ).fetchall()
    finally:
        con.close()

    # remove one of the two files
    primary_path1.unlink()

    load_manifest(rawpath, db_path)

    con = duckdb.connect(db_path)

    # Check from all three tables
    assert (
        con.execute(
            "SELECT COUNT(*) FROM imu_processing_status WHERE file_id = ?",
            [file_id_of_interest],
        ).fetchone()[0]
        == 1
    )

    # 8 seconds, window_length = 2 seconds; 8/2 = 4
    assert (
        con.execute(
            "SELECT COUNT(*) FROM imu_window_summary WHERE file_id = ?",
            [file_id_of_interest],
        ).fetchone()[0]
        == 4
    )

    assert (
        con.execute(
            "SELECT COUNT(*) FROM file_manifest WHERE file_id = ?",
            [file_id_of_interest],
        ).fetchone()[0]
        == 1
    )

    calls = []

    def record_call(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(
        "hbcd_data_platform.orchestration.process_imu_file",
        record_call,
    )
    # Run one more time - no re-processing
    run_imu_processing(con, rawpath)

    summaries_after = con.execute(
        """
        SELECT *
        FROM imu_window_summary
        WHERE file_id = ?
        ORDER BY window_index
        """,
        [file_id_of_interest],
    ).fetchall()
    status_after = con.execute(
        """
        SELECT *
        FROM imu_processing_status
        WHERE file_id = ?
        """,
        [file_id_of_interest],
    ).fetchall()

    assert calls == []

    assert summaries_before == summaries_after

    assert status_before == status_after

    con.close()


def test_file_removed_before_processing_will_be_skipped(tmp_path, monkeypatch):
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

    primary_path1.unlink()

    with duckdb.connect(db_path) as con:
        calls = []

        def record_call(*args, **kwargs):
            calls.append(args)

        monkeypatch.setattr(
            "hbcd_data_platform.orchestration.process_imu_file",
            record_call,
        )
        # Run once - no processing
        run_imu_processing(con, rawpath)

        assert calls == []


def test_reappeared_file_with_unchanged_metadata_is_not_reprocessed(
    tmp_path, monkeypatch
):
    rawpath = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"

    motion_path = rawpath / "sub-7236112352/ses-V02/motion"
    motion_path.mkdir(parents=True, exist_ok=True)

    filename = (
        "sub-7236112352_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.parquet"
    )

    primary_path = motion_path / filename

    # 200 rows (8 seconds = 200 / 25)
    make_synthetic_imu_parquet(primary_path)

    load_manifest(rawpath, db_path)

    con = duckdb.connect(db_path)
    try:
        run_imu_processing(con, rawpath)

        # size_bytes, modified_at
        size_before, modified_before = con.execute(
            """
            SELECT processed_size_bytes, processed_modified_at
            FROM imu_processing_status
            """
        ).fetchone()

        file_id_before = con.execute(
            "SELECT file_id FROM file_manifest WHERE relative_path=?",
            [str(primary_path.relative_to(rawpath))],
        ).fetchone()[0]

        backup_path = tmp_path / "backup.parquet"
        shutil.copy2(primary_path, backup_path)
        primary_path.unlink()

        load_manifest(rawpath, db_path)
        shutil.copy2(backup_path, primary_path)

        load_manifest(rawpath, db_path)

        size_restored, modified_restored = con.execute(
            """
            SELECT size_bytes, modified_at
            FROM file_manifest
            WHERE relative_path=?
            """,
            [str(primary_path.relative_to(rawpath))],
        ).fetchone()

        file_id_after = con.execute(
            "SELECT file_id FROM file_manifest WHERE relative_path=?",
            [str(primary_path.relative_to(rawpath))],
        ).fetchone()[0]

        assert size_before == size_restored
        assert modified_before == modified_restored
        assert file_id_before == file_id_after

        calls = []

        def record_call(*args, **kwargs):
            calls.append(args)

        monkeypatch.setattr(
            "hbcd_data_platform.orchestration.process_imu_file",
            record_call,
        )
        # Run once - no processing
        run_imu_processing(con, rawpath)

        assert calls == []
    finally:
        con.close()


def test_reappeared_file_with_changed_metadata_is_reprocessed(tmp_path, monkeypatch):
    rawpath = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"

    motion_path = rawpath / "sub-7236112352/ses-V02/motion"
    motion_path.mkdir(parents=True, exist_ok=True)

    filename = (
        "sub-7236112352_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.parquet"
    )

    primary_path = motion_path / filename
    # 200 rows (8 seconds = 200 / 25)
    make_synthetic_imu_parquet(primary_path)

    load_manifest(rawpath, db_path)

    con = duckdb.connect(db_path)
    try:
        run_imu_processing(con, rawpath)

        file_id_before = con.execute(
            "SELECT file_id FROM file_manifest WHERE relative_path=?",
            [str(primary_path.relative_to(rawpath))],
        ).fetchone()[0]

        # size_bytes, modified_at
        size_before, modified_before = con.execute(
            """
            SELECT processed_size_bytes, processed_modified_at
            FROM imu_processing_status
            WHERE file_id = ?
            """,
            [file_id_before],
        ).fetchone()

        backup_path = tmp_path / "backup.parquet"
        shutil.copyfile(primary_path, backup_path)
        primary_path.unlink()

        load_manifest(rawpath, db_path)
        shutil.copyfile(backup_path, primary_path)

        original_mtime = backup_path.stat().st_mtime
        os.utime(
            primary_path,
            (original_mtime + 60, original_mtime + 60),
        )

        load_manifest(rawpath, db_path)

        size_restored, modified_restored = con.execute(
            """
            SELECT size_bytes, modified_at
            FROM file_manifest
            WHERE relative_path=?
            """,
            [str(primary_path.relative_to(rawpath))],
        ).fetchone()

        file_id_after = con.execute(
            "SELECT file_id FROM file_manifest WHERE relative_path=?",
            [str(primary_path.relative_to(rawpath))],
        ).fetchone()[0]

        assert size_before == size_restored
        assert modified_before != modified_restored
        assert file_id_before == file_id_after

        original = orchestration_module.process_imu_file
        spy = Mock(wraps=original)

        monkeypatch.setattr(
            orchestration_module,
            "process_imu_file",
            spy,
        )
        # Run once - processing once
        run_imu_processing(con, rawpath)

        spy.assert_called_once()

        size_postproc, modified_postproc = con.execute(
            """
            SELECT processed_size_bytes, processed_modified_at
            FROM imu_processing_status
            WHERE file_id = ?
            """,
            [file_id_after],
        ).fetchone()

        assert size_restored == size_postproc
        assert modified_restored == modified_postproc

    finally:
        con.close()


def test_repeated_orchestration_with_changed_window_seconds_reprocess(tmp_path):
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
        run_imu_processing(con, rawpath, window_seconds=2.0)

        assert (
            con.execute(
                "SELECT COUNT(*) FROM imu_window_summary WHERE file_id = ?", [file_id]
            ).fetchone()[0]
            == 4
        )
        assert (
            con.execute(
                "SELECT window_seconds FROM imu_processing_status WHERE file_id = ?",
                [file_id],
            ).fetchone()[0]
            == 2.0
        )

        # Run the function again with a different window length
        run_imu_processing(con, rawpath, window_seconds=4.0)

        assert (
            con.execute(
                "SELECT COUNT(*) FROM imu_window_summary WHERE file_id = ?", [file_id]
            ).fetchone()[0]
            == 2
        )
        assert (
            con.execute(
                "SELECT window_seconds FROM imu_processing_status WHERE file_id = ?",
                [file_id],
            ).fetchone()[0]
            == 4.0
        )
    finally:
        con.close()


def test_file_changed_after_scan_prevents_further_processing(tmp_path):
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

    try:
        con.execute(
            "CREATE TEMP TABLE imu_test AS SELECT * FROM read_parquet(?);",
            [str(primary_path1)],
        )

        # Hope it changes: modified_at & size_bytes
        con.execute(
            f"""
            UPDATE imu_test
            SET LeftAnkle_ACCEL_y = $value
            WHERE imu_latency = $timestamp
            """,
            {"value": None, "timestamp": 4.0},
        )

        con.execute(
            "COPY imu_test TO $output_path (FORMAT parquet)",
            {"output_path": str(primary_path1)},
        )

        # Need to get an id.
        file_id = con.execute(
            """
            SELECT file_id
            FROM file_manifest
            WHERE filename = ?;
            """,
            [filename1],
        ).fetchone()[0]

        with pytest.raises(ValueError, match="File changed before processing"):
            process_imu_file(con, file_id, rawpath, window_seconds=2.0)
    finally:
        con.close()


def test_file_changed_during_processing_will_thwart_updates(tmp_path, monkeypatch):
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

    try:
        # Need to get an id.
        file_id = con.execute(
            """
            SELECT file_id
            FROM file_manifest
            WHERE filename = ?;
            """,
            [filename1],
        ).fetchone()[0]

        # process once to set a reference point.
        run_imu_processing(con, rawpath, window_seconds=2.0)

        summaries_before = con.execute(
            """
            SELECT * FROM imu_window_summary
            WHERE file_id = ? ORDER BY window_index
            """,
            [file_id],
        ).fetchall()

        def summarize_then_change(file_path, window_seconds):
            summaries = summarize_imu_windows(file_path, window_seconds=window_seconds)

            stat = file_path.stat()
            os.utime(
                file_path,
                ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000),
            )

            return summaries

        monkeypatch.setattr(
            orchestration_module.imu_module,
            "summarize_imu_windows",
            summarize_then_change,
        )

        with pytest.raises(ValueError, match="File changed during processing"):
            process_imu_file(con, file_id, rawpath, window_seconds=4.0)

        summaries_after = con.execute(
            """
            SELECT * FROM imu_window_summary
            WHERE file_id = ? ORDER BY window_index
            """,
            [file_id],
        ).fetchall()

        # Now make sure that imu_processing_status has the record of window_seconds:2.0
        assert summaries_before == summaries_after
        assert (
            con.execute(
                "SELECT window_seconds FROM imu_processing_status WHERE file_id = ?",
                [file_id],
            ).fetchone()[0]
            == 2.0
        )

    finally:
        con.close()
