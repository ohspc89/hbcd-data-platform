import math
from pathlib import Path

import duckdb

def summarize_imu_timestamps(path: Path) -> dict[str, int | float]:
    con = duckdb.connect()

    try:
        row = con.execute(
            """
            WITH imu_data AS (
                SELECT 
                    ROW_NUMBER() OVER () AS row_num,
                    imu_latency
                FROM read_csv(
                    ?,
                    delim = '\t',
                    header = true,
                    types = {'imu_latency': 'DOUBLE'}
                    )
            ), intervals AS (
                SELECT
                    imu_latency,
                    imu_latency - LAG(imu_latency) OVER (ORDER BY row_num)
                    AS interval_s
                FROM imu_data
            )
            SELECT
                COUNT(*),
                MIN(imu_latency),
                MAX(imu_latency),
                MIN(interval_s),
                MAX(interval_s),
                COUNT(*) FILTER (
                    WHERE imu_latency IS NULL
                ) AS null_timestamp_count,
                COUNT(interval_s) AS interval_count,
            FROM intervals;
            """,
            [str(path)]
        ).fetchone()

        if row[0] == 0:
            raise ValueError(f"IMU file contains no samples: '{path}'")

        return {
            "sample_count": row[0],
            "start_s": row[1],
            "end_s": row[2],
            "min_interval_s": row[3],
            "max_interval_s": row[4],
            "null_timestamp_count": row[5],
            "interval_count": row[6],
        }

    finally:
        con.close()


def validate_imu_timestamps(
    path: Path,
    expected_hz: float = 25.0,
    tolerance_s: float = 1e-6,
) -> dict:
    if expected_hz <= 0:
        raise ValueError("expected_hz must be greater than zero")

    summary = summarize_imu_timestamps(path)
    expected_interval_s = 1 / expected_hz

    min_interval = summary["min_interval_s"] 
    max_interval = summary["max_interval_s"] 

    intervals_are_valid = (
        summary["sample_count"] >= 2
        and summary["null_timestamp_count"] == 0
        and summary["interval_count"] == summary["sample_count"] - 1
        and min_interval is not None
        and max_interval is not None
        and math.isclose(
            min_interval,
            expected_interval_s,
            abs_tol=tolerance_s)
        and math.isclose(
            max_interval,
            expected_interval_s,
            abs_tol=tolerance_s)
    )

    return {
        "status": "PASS" if intervals_are_valid else "FAIL",
        "sample_count": summary["sample_count"],
        "null_timestamp_count": summary["null_timestamp_count"],
        "interval_count": summary["interval_count"],
        "min_interval_s": min_interval,
        "max_interval_s": max_interval,
        "expected_interval_s": expected_interval_s,
        "tolerance_s": tolerance_s,
    }
