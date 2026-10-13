import csv
import math
from pathlib import Path
import re

from collections import Counter
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
            [str(path)],
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
        and math.isclose(min_interval, expected_interval_s, abs_tol=tolerance_s)
        and math.isclose(max_interval, expected_interval_s, abs_tol=tolerance_s)
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


def expected_imu_columns(path: Path) -> list[str]:
    # find task-(Left|Right)LegMovement from filename
    task_pattern = re.compile(r"(?:^|_)task-(Left|Right)LegMovement(?=_|$)")
    match = task_pattern.search(path.stem)
    if match is not None:
        leg = match.group(1)
    else:
        raise ValueError(f"Unsupported or missing IMU task: {path}")

    return [
        "imu_latency",
        f"{leg}Ankle_ACCEL_x",
        f"{leg}Ankle_ACCEL_y",
        f"{leg}Ankle_ACCEL_z",
        f"{leg}Ankle_GYRO_x",
        f"{leg}Ankle_GYRO_y",
        f"{leg}Ankle_GYRO_z",
    ]


def validate_imu_schema(path: Path) -> dict:
    expected_columns = expected_imu_columns(path)

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        observed_columns = next(reader, [])

    missing = set(expected_columns) - set(observed_columns)
    extra = set(observed_columns) - set(expected_columns)
    counts = Counter(observed_columns)
    duplicates = sorted(name for name, count in counts.items() if count > 1)

    if len(missing) == len(extra) == len(duplicates) == 0:
        status = "PASS"
    else:
        status = "FAIL"

    return {
        "status": status,
        "missing_columns": sorted(missing),
        "extra_columns": sorted(extra),
        "duplicate_columns": duplicates,
    }


def summarize_imu_sensor_qc(
    path: Path,
    *,
    accel_saturation_threshold: float,
    gyro_saturation_threshold: float,
    accel_measurement_limit: float = 16,
    gyro_measurement_limit: float = 2000,
) -> list[dict]:
    sensor_columns = expected_imu_columns(path)[1:]

    if any(
        (
            accel_saturation_threshold <= 0,
            gyro_saturation_threshold <= 0,
            accel_measurement_limit <= 0,
            gyro_measurement_limit <= 0,
            accel_saturation_threshold > accel_measurement_limit,
            gyro_saturation_threshold > gyro_measurement_limit,
            math.isnan(accel_saturation_threshold),
            math.isinf(accel_saturation_threshold),
            math.isnan(accel_measurement_limit),
            math.isinf(accel_measurement_limit),
            math.isnan(gyro_saturation_threshold),
            math.isinf(gyro_saturation_threshold),
            math.isnan(gyro_measurement_limit),
            math.isinf(gyro_measurement_limit),
        )
    ):
        raise ValueError(f"invalid threshold: '{accel_saturation_threshold}'")

    aggregate_parts = []

    for column in sensor_columns:
        if "ACCEL" in column:
            limit_param = "$accel_measurement_limit"
            threshold_param = "$accel_saturation_threshold"
        else:
            limit_param = "$gyro_measurement_limit"
            threshold_param = "$gyro_saturation_threshold"

        aggregate_parts.append(
            f"""
            COALESCE(
                SUM(
                    CASE WHEN "{column}" IS NULL
                    THEN 1 ELSE 0 END),
                0
            ) AS {column}_null_count,
            COALESCE(
                SUM(
                    CASE WHEN "{column}" >{limit_param}
                    OR "{column}" < -{limit_param}
                    THEN 1 ELSE 0 END),
                0
            ) AS {column}_out_of_range_count,
            COALESCE(
                SUM(
                    CASE WHEN "{column}" >= {threshold_param}
                    OR "{column}" <= -{threshold_param}
                    THEN 1 ELSE 0 END),
                0
            ) AS {column}_saturation_count
            """
        )

    query = f"""
        SELECT
            COUNT(*) AS sample_count,
            {", ".join(aggregate_parts)}
        FROM read_parquet($input_path)
    """

    con = duckdb.connect()
    try:
        row = con.execute(
            query,
            {
                "input_path": str(path),
                "accel_measurement_limit": accel_measurement_limit,
                "accel_saturation_threshold": accel_saturation_threshold,
                "gyro_measurement_limit": gyro_measurement_limit,
                "gyro_saturation_threshold": gyro_saturation_threshold,
            },
        ).fetchone()
        output = []

        for index, column in enumerate(sensor_columns):
            offset = 1 + index * 3
            output.append(
                {
                    "column_name": column,
                    "sample_count": row[0],
                    "null_count": row[offset],
                    "out_of_range_count": row[offset+1],
                    "saturation_count": row[offset+2],
                }
            )
        return output
    finally:
        con.close()
