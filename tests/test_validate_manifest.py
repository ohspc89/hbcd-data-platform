from pathlib import Path
import duckdb
import pandas as pd
import pytest
from hbcd_data_platform.load_manifest import load_manifest
import hbcd_data_platform.validate_manifest as validation_module
from hbcd_data_platform.validate_manifest import (
    validate_participant_sessions,
    validate_session_scans,
    save_validation_results,
)


@pytest.fixture
def test_paths(tmp_path):
    raw_path = tmp_path / "rawdata"
    db_path = tmp_path / "test.duckdb"
    if not raw_path.is_dir():
        raw_path.mkdir()

    return raw_path, db_path


def test_missing_participant_sessions_returns_fail(test_paths):
    """
    Given:
        One participant with no `_sessions.tsv`
    When:
        validate_participant_sessions()
    Then:
        returns FAIL
    """

    raw_path, db_path = test_paths

    sub1 = "sub-3341280012"
    sub2 = "sub-7381023315"

    file = raw_path / "participants.tsv"
    file.write_text(f"participant_id\tsex\n{sub1}\tMale\n{sub2}\tFemale\n")

    # Make two participants, with one missing sessions.tsv
    sub1_sessions = raw_path / sub1 / f"{sub1}_sessions.tsv"
    sub1_sessions_sidecar = raw_path / sub1 / f"{sub1}_sessions.json"
    sub2_sessions_sidecar = raw_path / sub2 / f"{sub2}_sessions.json"

    (raw_path / sub1).mkdir()
    (raw_path / sub2).mkdir()

    sub1_sessions.write_text(
        "session_id\tsite\tage\tage_adjusted\thead_size\n"
        "ses-V02\thbcdsite57\t0.023\t9\t58\n"
    )
    sidecar_text = """
        {
            "site": {
                "Description": "Site where the session data was collected",
                "Levels": [
                    "hbcdsite89",
                    "hbcdsite64",
                    "hbcdsite02",
                    "hbcdsite57"
                    ]
                },
            "age": {
                "Description": "Age (in years) of the candidate at the time of the session",
                "Units": "years"
                },
            "age_adjusted": {
                "Description": "Adjusted chronological age (in days) based on the EDD",
                "Units": "days"
                },
            "head_size": {
                "Description": "Head size",
                "Units": "centimeters"
                }
        }
        """
    sub1_sessions_sidecar.write_text(sidecar_text)
    sub2_sessions_sidecar.write_text(sidecar_text)

    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)
    result = validate_participant_sessions(con)
    df = result.fetchdf()

    sub1_id = sub1.split("-", 1)[1]
    sub2_id = sub2.split("-", 1)[1]

    assert df.loc[df["participant_id"] == sub1_id, "observed"].iloc[0] == 1
    assert df.loc[df["participant_id"] == sub2_id, "observed"].iloc[0] == 0
    assert df.loc[df["participant_id"] == sub1_id, "status"].iloc[0] == "PASS"
    assert df.loc[df["participant_id"] == sub2_id, "status"].iloc[0] == "FAIL"
    assert (
        df.loc[df["participant_id"] == sub1_id, "rule"].iloc[0]
        == "participant_sessions"
    )
    assert df.loc[df["participant_id"] == sub1_id, "expected"].iloc[0] == 1

    con.close()


def test_missing_session_scans_returns_fail(test_paths):

    raw_path, db_path = test_paths

    sub1 = "sub-3341628129"

    (raw_path / sub1 / "ses-V02").mkdir(parents=True)
    (raw_path / sub1 / "ses-V03").mkdir(parents=True)

    tsv_file = raw_path / sub1 / f"ses-V02/{sub1}_ses-V02_scans.tsv"
    json_sidecar = raw_path / sub1 / f"ses-V03/{sub1}_ses-V03_scans.json"

    tsv_file.write_text(
        "session_id\tsite\tage\tage_adjusted\thead_size\n"
        "ses-V02\thbcdsite57\t0.023\t9\t58\n"
    )
    sidecar_text = """
        {
            "site": {
                "Description": "Site where the session data was collected",
                "Levels": [
                    "hbcdsite89",
                    "hbcdsite64",
                    "hbcdsite02",
                    "hbcdsite57"
                    ]
                },
            "age": {
                "Description": "Age (in years) of the candidate at the time of the session",
                "Units": "years"
                },
            "age_adjusted": {
                "Description": "Adjusted chronological age (in days) based on the EDD",
                "Units": "days"
                },
            "head_size": {
                "Description": "Head size",
                "Units": "centimeters"
                }
        }
        """
    json_sidecar.write_text(sidecar_text)

    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)
    result = validate_session_scans(con)
    df = result.fetchdf()

    assert df.loc[df["session_id"] == "V02", "observed"].iloc[0] == 1
    assert df.loc[df["session_id"] == "V03", "observed"].iloc[0] == 0
    assert df.loc[df["session_id"] == "V02", "status"].iloc[0] == "PASS"
    assert df.loc[df["session_id"] == "V03", "status"].iloc[0] == "FAIL"


def test_validation_rollback_preserves_existing_results(monkeypatch, test_paths):
    raw_path, db_path = test_paths

    sub1 = "sub-3341705129"

    file = raw_path / "participants.tsv"
    file.write_text(f"participant_id\tsex\n{sub1}\tMale\n")

    sub1_sessions = raw_path / sub1 / f"{sub1}_sessions.tsv"

    (raw_path / sub1).mkdir()

    sub1_sessions.write_text(
        "session_id\tsite\tage\tage_adjusted\thead_size\n"
        "ses-V02\thbcdsite57\t0.023\t9\t58\n"
    )

    def fake_insert(con, result):
        count = con.sql("SELECT COUNT(*) FROM validation_results").fetchone()[0]

        assert count == 0

        raise RuntimeError("Simulated INSERT failure")


    load_manifest(raw_path, db_path)

    con = duckdb.connect(db_path)

    try:
        save_validation_results(con)

        before = con.sql(
            """
            SELECT *
            FROM validation_results
            ORDER BY participant_id, rule;
            """
        ).fetchdf()

        assert len(before) > 0

        monkeypatch.setattr(
            validation_module,
            "insert_validation_results",
            fake_insert,
        )

        with pytest.raises(RuntimeError, match="Simulated INSERT failure"):
            save_validation_results(con)

        after = con.sql(
            """
            SELECT *
            FROM validation_results
            ORDER BY participant_id, rule;
            """
        ).fetchdf()

        pd.testing.assert_frame_equal(before, after)

    finally:
        con.close()
