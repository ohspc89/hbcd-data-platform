from pathlib import Path

import duckdb
import pandas as pd

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent


def test_session_readiness(tmp_path):
    # 1. Create an isolated test database
    db_path = tmp_path / "test.duckdb"
    con = duckdb.connect(db_path)

    # 2. Load synthetic fixture data
    fixture_path = TEST_DIR / "fixtures/session_readiness_practice.sql"
    con.execute(fixture_path.read_text())

    # 3. Execute session_readiness.sql
    query_sql = PROJECT_ROOT / "sql/session_readiness.sql"
    actual = con.execute(query_sql.read_text()).fetchdf()

    # 4. Load expected_session_readiness.csv
    expected = pd.read_csv(
        TEST_DIR / "fixtures/expected_session_readiness.csv",
        dtype={"participant_id": str, "session_id": str},
    )

    bool_columns = [
        "has_scans",
        "has_left_primary",
        "has_right_primary",
        "has_left_calibration",
        "has_right_calibration",
        "ready_for_imu_qc",
    ]

    expected[bool_columns] = expected[bool_columns].astype(bool)

    print(actual)
    print(expected)

    # 5. Compare
    pd.testing.assert_frame_equal(actual, expected)

