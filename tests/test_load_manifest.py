from pathlib import Path
import pandas as pd
import duckdb
import pytest
from unittest.mock import MagicMock
import hbcd_data_platform.load_manifest as load_manifest_module
from hbcd_data_platform.load_manifest import load_manifest


@pytest.fixture
def test_paths(tmp_path):
    raw_path = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"
    if not raw_path.is_dir():
        raw_path.mkdir()

    return raw_path, db_path


def test_initial_load(tmp_path):
    """
    Given:
        a raw-data fixture containing N (e.g., 5) files

    When:
        load_manifest()

    Then:
        COUNT(*) == N
    """

    raw_path = Path("tests/fixtures/rawdata")
    db_path = tmp_path / "test.duckdb"

    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)

    actual_count = con.sql("SELECT COUNT(*) FROM file_manifest;")

    true_files = [
        x for x in raw_path.rglob("*") if x.is_file() and not x.name.startswith(".")
    ]
    assert actual_count.fetchone()[0] == len(true_files)

    con.close()


def test_repeated_load_does_not_duplicate_files(tmp_path):
    """
    Given:
        fresh DB + fixture containing N files

    When:
        load_manifest(raw_path, db_path)
        load_manifest(raw_path, db_path)

    Then:
        COUNT(*) = N
    """
    raw_path = Path("tests/fixtures/rawdata")
    db_path = tmp_path / "test.duckdb"

    load_manifest(raw_path, db_path)
    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)

    actual_count = con.sql("SELECT COUNT(*) FROM file_manifest;")

    true_files = [
        x for x in raw_path.rglob("*") if x.is_file() and not x.name.startswith(".")
    ]
    assert actual_count.fetchone()[0] == len(true_files)

    con.close()


def test_repeated_load_preserves_file_id(tmp_path):
    """
    Given:
        fresh DB

    When:
        Run #1
        SELECT relative_path, file_id
        first state saved
        Run #2
        SELECT relative_path, file_id
        second state saved

    Then:
        first == second
    """
    raw_path = Path("tests/fixtures/rawdata")
    db_path = tmp_path / "test.duckdb"

    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)
    first_ids = dict(
        con.sql("SELECT relative_path, file_id FROM file_manifest;").fetchall()
    )

    con.close()

    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)
    second_ids = dict(
        con.sql("SELECT relative_path, file_id FROM file_manifest;").fetchall()
    )

    con.close()

    assert first_ids == second_ids


def test_changed_file_updates_metadata_without_changing_identity(test_paths):
    """
    Given:
        fake raw directory, a file

    When:
        Run #1:
        load_manifest() -> file_id, size_bytes, modified_at, discovered_at saved

        Modify source file

        Run #2:
        load_manifest()

    Expect:
        file_id         SAME
        relative_path   SAME
        size_bytes      CHANGED
        modified_at     CHANGED
        discovered_at   SAME
    """
    # raw_path = tmp_path / "rawdata"
    # db_path = tmp_path / "test.duckdb"
    # raw_path.mkdir()
    raw_path, db_path = test_paths

    source_file = raw_path / "participants.tsv"
    source_file.write_text("participant_id\tsex\nsub-3710923819\tMale\n")

    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)
    (
        before_file_id,
        before_relative_path,
        before_size_bytes,
        before_modified_at,
        before_discovered_at,
    ) = con.sql(
        "SELECT file_id, relative_path, size_bytes, modified_at, discovered_at FROM file_manifest;"
    ).fetchone()
    con.close()

    source_file.write_text(
        "participant_id\tsex\nsub-3710923819\tMale\nsub-1728302816\tFemale\n"
    )

    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)
    (
        after_file_id,
        after_relative_path,
        after_size_bytes,
        after_modified_at,
        after_discovered_at,
    ) = con.sql(
        "SELECT file_id, relative_path, size_bytes, modified_at, discovered_at FROM file_manifest;"
    ).fetchone()
    con.close()

    assert before_file_id == after_file_id
    assert before_relative_path == after_relative_path
    assert before_size_bytes < after_size_bytes
    assert before_discovered_at == after_discovered_at


def test_new_file_is_inserted_on_repeated_load(test_paths):
    """
    Given:
        One file exists in the directory

    When:
        Run #1
        new file created in the directory

        Run #2

    Then:
        new file properly counted
    """
    raw_path, db_path = test_paths
    # raw_path = tmp_path / "rawdata"
    # db_path = tmp_path / "test.duckdb"
    # raw_path.mkdir()

    initial_file = raw_path / "participants.tsv"
    initial_file.write_text("participant_id\tsex\nsub-3710923819\tMale\n")

    load_manifest(raw_path, db_path)

    new_participant_id = "sub-1234567890"
    new_file_dir = raw_path / new_participant_id
    new_file_dir.mkdir()

    new_file = new_file_dir / f"{new_participant_id}_sessions.tsv"
    new_file.write_text(
        "session_id\tsite\tage\tage_adjusted\theade_size\nses-V02\thbcdsite27\t0.717\t59\t66\n"
    )

    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)
    new_df = con.sql(
        """
        SELECT
            relative_path,
            participant_id,
            suffix,
            discovered_at,
            last_seen_at
        FROM file_manifest;
        """
    ).fetchdf()
    con.close()

    expected_path = f"{new_participant_id}/{new_participant_id}_sessions.tsv"
    new_row = new_df.loc[new_df["relative_path"] == expected_path]

    assert len(new_row) == 1

    row = new_row.iloc[0]
    assert row["suffix"] == "sessions"
    assert row["participant_id"] == new_participant_id.split("-", 1)[1]
    assert row["discovered_at"] == row["last_seen_at"]


def test_repeated_load_preserves_discovered_at_and_updates_last_seen_at(test_paths):

    raw_path, db_path = test_paths

    file = raw_path / "participants.tsv"
    file.write_text("participant_id\tsex\nsub-3341280012\tMale\n")

    t1 = pd.Timestamp("2026-01-01 12:00:00")
    t2 = pd.Timestamp("2026-01-02 12:00:00")

    load_manifest(raw_path, db_path, scan_time=t1)
    load_manifest(raw_path, db_path, scan_time=t2)

    con = duckdb.connect(db_path)
    discovered_at, last_seen_at = con.sql(
        """
        SELECT
            discovered_at, last_seen_at
        FROM file_manifest
        WHERE relative_path = 'participants.tsv';
        """
    ).fetchone()
    con.close()

    assert discovered_at == t1
    assert last_seen_at == t2


def test_scan_failure_raises_runtime_error(monkeypatch, test_paths):

    raw_path, db_path = test_paths

    def fake_scan_files(path):
        raise RuntimeError("Simulated scan failure")

    monkeypatch.setattr(
        load_manifest_module,
        "scan_files",
        fake_scan_files,
    )

    fake_connection = MagicMock()
    monkeypatch.setattr(
        load_manifest_module.duckdb, "connect", lambda db_path: fake_connection
    )

    with pytest.raises(RuntimeError, match="Simulated scan failure"):
        load_manifest(raw_path, db_path)

    fake_connection.close.assert_called_once()
