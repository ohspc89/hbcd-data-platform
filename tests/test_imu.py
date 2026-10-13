import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

import duckdb

from conftest import make_synthetic_imu_tsv, make_synthetic_imu_parquet
from hbcd_data_platform.imu import (
    expected_imu_columns,
    summarize_imu_sensor_qc,
    summarize_imu_timestamps,
    validate_imu_schema,
    validate_imu_timestamps,
)


def test_evaluate_tsv(tmp_path):

    for side in ["Left", "Right"]:
        fname = (
            f"sub-0001_ses-V02_task-{side}LegMovement"
            "_tracksys-imu_acq-primary_motion.tsv"
        )
        make_synthetic_imu_tsv(tmp_path / fname)

        df = pd.read_csv(tmp_path / fname, sep="\t")

        assert list(df.columns) == [
            "imu_latency",
            f"{side}Ankle_ACCEL_x",
            f"{side}Ankle_ACCEL_y",
            f"{side}Ankle_ACCEL_z",
            f"{side}Ankle_GYRO_x",
            f"{side}Ankle_GYRO_y",
            f"{side}Ankle_GYRO_z",
        ]

        assert len(df) == 200
        assert df.iloc[0]["imu_latency"] == pytest.approx(0.0)
        assert df.iloc[-1]["imu_latency"] == pytest.approx(7.96)
        intervals = df["imu_latency"].diff().dropna().tolist()
        assert intervals == pytest.approx([0.04] * 199)
        assert df.isna().sum().sum() == 0
        accel_columns = [
            f"{side}Ankle_ACCEL_x",
            f"{side}Ankle_ACCEL_y",
            f"{side}Ankle_ACCEL_z",
        ]
        gyro_columns = [
            f"{side}Ankle_GYRO_x",
            f"{side}Ankle_GYRO_y",
            f"{side}Ankle_GYRO_z",
        ]
        assert df[accel_columns].ge(-16).all().all()
        assert df[accel_columns].le(16).all().all()
        assert df[gyro_columns].ge(-2000).all().all()
        assert df[gyro_columns].le(2000).all().all()


def test_filename_without_task_raises_value_error(tmp_path):
    fname = "sub-0001_ses-V02_tracksys-imu_acq-primary_motion.tsv"
    with pytest.raises(ValueError):
        make_synthetic_imu_tsv(tmp_path / fname)


def test_filename_with_invalid_task_raises_value_error(tmp_path):
    fname = "sub-0001_ses-V02_task-SquidLegMovement_tracksys-imu_acq-primary_motion.tsv"
    with pytest.raises(ValueError):
        make_synthetic_imu_tsv(tmp_path / fname)


def test_summarize_imu_timestamps_returns_expected_values(tmp_path):
    fname = f"sub-0001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    make_synthetic_imu_tsv(tmp_path / fname)

    out = summarize_imu_timestamps(tmp_path / fname)
    assert out["sample_count"] == 200
    assert out["start_s"] == pytest.approx(0.0)
    assert out["end_s"] == pytest.approx(7.96)
    assert out["min_interval_s"] == pytest.approx(0.04)
    assert out["max_interval_s"] == pytest.approx(0.04)


def test_file_with_header_only_raises_value_error(tmp_path):
    fname = "sub-0001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    fpath = tmp_path / fname
    fpath.write_text(
        "imu_latency\tLeftAnkle_ACCEL_x\tLeftAnkle_ACCEL_y\tLeftAnkle_ACCEL_z\tLeftAnkle_GYRO_x\tLeftAnkle_GYRO_y\tLeftAnkle_GYRO_z\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="contains no samples"):
        summarize_imu_timestamps(fpath)


def test_normal_sampling_hz(tmp_path):
    fname = f"sub-0001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    validation = validate_imu_timestamps(fpath)
    assert validation["status"] == "PASS"


def test_timestamp_summary_detects_missing_sample(tmp_path):
    fname = f"sub-0001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    df = pd.read_csv(fpath, sep="\t")
    df.drop(index=100, inplace=True)
    df.to_csv(fpath, sep="\t", index=False)

    validation = validate_imu_timestamps(fpath)
    assert validation["sample_count"] == 199
    assert validation["min_interval_s"] == pytest.approx(0.04)
    assert validation["max_interval_s"] == pytest.approx(0.08)
    assert validation["status"] == "FAIL"


def test_timestamp_summary_detects_out_of_order_sample(tmp_path):
    fname = f"sub-0001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    df = pd.read_csv(fpath, sep="\t")
    df.iloc[[100, 101]] = df.iloc[[101, 100]].to_numpy()
    df.to_csv(fpath, sep="\t", index=False)

    validation = validate_imu_timestamps(fpath)
    assert validation["sample_count"] == 200
    assert validation["min_interval_s"] == pytest.approx(-0.04)
    assert validation["max_interval_s"] == pytest.approx(0.08)
    assert validation["status"] == "FAIL"


def test_timestamp_summary_detects_duplicate_samples(tmp_path):
    fname = f"sub-0001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    df = pd.read_csv(fpath, sep="\t")
    df.iloc[100] = df.iloc[99].to_numpy()
    df.to_csv(fpath, sep="\t", index=False)

    validation = validate_imu_timestamps(fpath)
    assert validation["sample_count"] == 200
    assert validation["min_interval_s"] == pytest.approx(0.00)
    assert validation["max_interval_s"] == pytest.approx(0.08)
    assert validation["status"] == "FAIL"


def test_timestamp_summary_detects_missing_timestamp(tmp_path):
    fname = f"sub-0001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    df = pd.read_csv(fpath, sep="\t")
    df.at[100, "imu_latency"] = pd.NA
    df.to_csv(fpath, sep="\t", index=False)

    validation = validate_imu_timestamps(fpath)
    assert validation["null_timestamp_count"] == 1
    assert validation["interval_count"] == 197
    assert validation["min_interval_s"] == pytest.approx(0.04)
    assert validation["max_interval_s"] == pytest.approx(0.04)
    assert validation["status"] == "FAIL"


def test_timestamp_summary_detects_single_sample(tmp_path):
    fname = f"sub-0001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    df = pd.read_csv(fpath, sep="\t")
    df = df.iloc[[0]]
    df.to_csv(fpath, sep="\t", index=False)

    validation = validate_imu_timestamps(fpath)
    assert validation["sample_count"] == 1
    assert validation["interval_count"] == 0
    assert validation["min_interval_s"] is None
    assert validation["max_interval_s"] is None
    assert validation["status"] == "FAIL"


def test_timestamp_summary_detects_different_expected_frequency(tmp_path):
    fname = f"sub-0001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    validation = validate_imu_timestamps(fpath, expected_hz=50)
    assert validation["status"] == "FAIL"


@pytest.mark.parametrize("expected_hz", [0, -25])
def test_invalid_expected_frequency_raises_value_error(tmp_path, expected_hz):
    fname = f"sub-0001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    with pytest.raises(ValueError, match="greater than zero"):
        validate_imu_timestamps(fpath, expected_hz=expected_hz)


@pytest.mark.parametrize(
    ("offset_s", "expected_status"),
    [
        (0.0000005, "PASS"),
        (0.0000020, "FAIL"),
    ],
)
def test_timestamp_tolerance_controls_validation_status(
    tmp_path, offset_s, expected_status
):
    fname = f"sub-0001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    df = pd.read_csv(fpath, sep="\t")
    df.at[42, "imu_latency"] = df.at[42, "imu_latency"] + offset_s
    df.to_csv(fpath, sep="\t", index=False)

    validation = validate_imu_timestamps(fpath)
    assert validation["status"] == expected_status
    assert validation["max_interval_s"] == pytest.approx(0.04 + offset_s)
    assert validation["min_interval_s"] == pytest.approx(0.04 - offset_s)


def test_expected_imu_columns_for_left_task(tmp_path):
    valid_left_task = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    )
    assert expected_imu_columns(valid_left_task) == [
        "imu_latency",
        "LeftAnkle_ACCEL_x",
        "LeftAnkle_ACCEL_y",
        "LeftAnkle_ACCEL_z",
        "LeftAnkle_GYRO_x",
        "LeftAnkle_GYRO_y",
        "LeftAnkle_GYRO_z",
    ]


def test_expected_imu_columns_for_right_task(tmp_path):
    valid_right_task = (
        tmp_path
        / "sub-2000000001_ses-V02_task-RightLegMovement_tracksys-imu_acq-primary_motion.tsv"
    )
    assert expected_imu_columns(valid_right_task) == [
        "imu_latency",
        "RightAnkle_ACCEL_x",
        "RightAnkle_ACCEL_y",
        "RightAnkle_ACCEL_z",
        "RightAnkle_GYRO_x",
        "RightAnkle_GYRO_y",
        "RightAnkle_GYRO_z",
    ]


def test_expected_imu_columns_rejects_invalid_task(tmp_path):
    no_task = tmp_path / "sub-2000000001_ses-V02_tracksys-imu_acq-primary_motion.tsv"
    invalid_task = (
        tmp_path
        / "sub-2000000001_ses-V02_task-SquidLegMovement_tracksys-imu_acq-primary_motion.tsv"
    )
    invalid_task_extra = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovementExtra_tracksys-imu_acq-primary_motion.tsv"
    )

    with pytest.raises(ValueError, match="missing IMU task"):
        expected_imu_columns(no_task)
    with pytest.raises(ValueError, match="Unsupported"):
        expected_imu_columns(invalid_task)
    with pytest.raises(ValueError, match="Unsupported"):
        expected_imu_columns(invalid_task_extra)


def test_validate_imu_columns_for_left_task(tmp_path):
    valid_left_task = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    )
    make_synthetic_imu_tsv(valid_left_task)
    out = validate_imu_schema(valid_left_task)

    assert out["status"] == "PASS"
    assert out["missing_columns"] == []
    assert out["extra_columns"] == []
    assert out["duplicate_columns"] == []


def test_validate_imu_columns_for_right_task(tmp_path):
    valid_right_task = (
        tmp_path
        / "sub-2000000001_ses-V02_task-RightLegMovement_tracksys-imu_acq-primary_motion.tsv"
    )
    make_synthetic_imu_tsv(valid_right_task)
    out = validate_imu_schema(valid_right_task)

    assert out["status"] == "PASS"
    assert out["missing_columns"] == []
    assert out["extra_columns"] == []
    assert out["duplicate_columns"] == []


def test_validate_missing_column(tmp_path):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-RightLegMovement_tracksys-imu_acq-primary_motion.tsv"
    )
    make_synthetic_imu_tsv(filepath)
    df = pd.read_csv(filepath, sep="\t")
    df.drop(columns="imu_latency", inplace=True)
    df.to_csv(filepath, sep="\t", index=False)

    out = validate_imu_schema(filepath)
    assert out["status"] == "FAIL"
    assert out["missing_columns"] == ["imu_latency"]
    assert out["extra_columns"] == []
    assert out["duplicate_columns"] == []


def test_validate_unexpected_column(tmp_path):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-RightLegMovement_tracksys-imu_acq-primary_motion.tsv"
    )
    make_synthetic_imu_tsv(filepath)
    df = pd.read_csv(filepath, sep="\t")
    # add an unexpected column
    df["unexpected"] = [0.12] * len(df)
    df.to_csv(filepath, sep="\t", index=False)

    out = validate_imu_schema(filepath)

    assert out["status"] == "FAIL"
    assert out["missing_columns"] == []
    assert out["extra_columns"] == ["unexpected"]
    assert out["duplicate_columns"] == []


def test_column_names_switched(tmp_path):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    )
    make_synthetic_imu_tsv(filepath)
    df = pd.read_csv(filepath, sep="\t")
    unexpected_columns = [
        "RightAnkle_ACCEL_x",
        "RightAnkle_ACCEL_y",
        "RightAnkle_ACCEL_z",
        "RightAnkle_GYRO_x",
        "RightAnkle_GYRO_y",
        "RightAnkle_GYRO_z",
    ]
    missing_columns = [
        "LeftAnkle_ACCEL_x",
        "LeftAnkle_ACCEL_y",
        "LeftAnkle_ACCEL_z",
        "LeftAnkle_GYRO_x",
        "LeftAnkle_GYRO_y",
        "LeftAnkle_GYRO_z",
    ]
    df.rename(
        columns=dict(zip(df.columns, ["imu_latency"] + unexpected_columns)),
        inplace=True,
    )
    df.to_csv(filepath, sep="\t", index=False)

    out = validate_imu_schema(filepath)

    assert out["status"] == "FAIL"
    assert out["missing_columns"] == missing_columns
    assert out["extra_columns"] == unexpected_columns
    assert out["duplicate_columns"] == []


def test_column_names_shuffled(tmp_path):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    )
    make_synthetic_imu_tsv(filepath)
    df = pd.read_csv(filepath, sep="\t")
    # shuffle columns
    df = df.iloc[:, [6, 2, 3, 1, 4, 0, 5]]
    df.to_csv(filepath, sep="\t", index=False)

    out = validate_imu_schema(filepath)

    assert out["status"] == "PASS"
    assert out["missing_columns"] == []
    assert out["extra_columns"] == []
    assert out["duplicate_columns"] == []


def test_duplicate_column_names(tmp_path):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    )
    make_synthetic_imu_tsv(filepath)
    df = pd.read_csv(filepath, sep="\t")
    df["duplicate"] = df["LeftAnkle_ACCEL_y"]
    df.rename(columns={"duplicate": "LeftAnkle_ACCEL_y"}, inplace=True)
    df.to_csv(filepath, sep="\t", index=False)

    out = validate_imu_schema(filepath)

    assert out["status"] == "FAIL"
    assert out["missing_columns"] == []
    assert out["extra_columns"] == []
    assert out["duplicate_columns"] == ["LeftAnkle_ACCEL_y"]


def test_validate_parquet_conversion(tmp_path):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv"
    )
    make_synthetic_imu_tsv(filepath)
    parquet_path = filepath.with_suffix(".parquet")
    con = duckdb.connect()
    try:
        # Read it, and save as a praquet
        con.execute(
            """
            COPY (
                SELECT *
                FROM read_csv($input_path, delim='\t', header=true)
            )
            TO $output_path (FORMAT parquet);
            """,
            {
                "input_path": str(filepath),
                "output_path": str(parquet_path),
            },
        )
        # Read the parquet, and check the following
        result = con.execute(
            """
            SELECT
                COUNT(*) AS sample_count,
                MIN(imu_latency) AS start_s,
                MAX(imu_latency) AS end_s
            FROM read_parquet(?);
            """,
            [str(parquet_path)],
        ).fetchone()

        assert result[0] == 200
        assert result[1] == pytest.approx(0.0)
        assert result[2] == pytest.approx(7.96)

        original = pd.read_csv(filepath, sep="\t")
        parquet = con.execute(
            "SELECT * FROM read_parquet(?);", [str(parquet_path)]
        ).fetchdf()

        assert list(parquet.columns) == list(original.columns)
        assert_frame_equal(original, parquet, check_dtype=False)
    finally:
        con.close()


@pytest.mark.parametrize(
    (
        "accel_col",
        "accel_x_oor_count",
        "accel_x_saturation_count",
        "accel_y_oor_count",
        "accel_y_saturation_count",
        "accel_z_oor_count",
        "accel_z_saturation_count",
    ),
    [
        ("LeftAnkle_ACCEL_x", 2, 2, 0, 0, 0, 0),
        ("LeftAnkle_ACCEL_y", 0, 0, 2, 2, 0, 0),
        ("LeftAnkle_ACCEL_z", 0, 0, 0, 0, 2, 2),
    ],
)
def test_imu_sensor_qc_over_accel_limit(
    tmp_path,
    accel_col,
    accel_x_oor_count,
    accel_x_saturation_count,
    accel_y_oor_count,
    accel_y_saturation_count,
    accel_z_oor_count,
    accel_z_saturation_count,
):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet"
    )
    make_synthetic_imu_parquet(filepath)

    con = duckdb.connect()
    try:
        con.execute(
            "CREATE TEMP TABLE imu_test AS SELECT * FROM read_parquet(?);",
            [str(filepath)],
        )

        con.execute(
            f"""
            UPDATE imu_test
            SET {accel_col} = $value
            WHERE imu_latency = $timestamp
            """,
            {"value": 16.1, "timestamp": 4.0},
        )

        con.execute(
            f"""
            UPDATE imu_test
            SET {accel_col} = $value
            WHERE imu_latency = $timestamp
            """,
            {"value": -16.1, "timestamp": 6.0},
        )

        con.execute(
            "COPY imu_test TO $output_path (FORMAT parquet)",
            {"output_path": str(filepath)},
        )
    finally:
        con.close()

    results = summarize_imu_sensor_qc(
        filepath, accel_saturation_threshold=15.5, gyro_saturation_threshold=1900
    )

    assert results[0]["sample_count"] == 200
    assert results[0]["null_count"] == 0
    assert results[0]["out_of_range_count"] == accel_x_oor_count
    assert results[0]["saturation_count"] == accel_x_saturation_count
    assert results[1]["sample_count"] == 200
    assert results[1]["null_count"] == 0
    assert results[1]["out_of_range_count"] == accel_y_oor_count
    assert results[1]["saturation_count"] == accel_y_saturation_count
    assert results[2]["sample_count"] == 200
    assert results[2]["null_count"] == 0
    assert results[2]["out_of_range_count"] == accel_z_oor_count
    assert results[2]["saturation_count"] == accel_z_saturation_count


@pytest.mark.parametrize(
    (
        "gyro_col",
        "gyro_x_oor_count",
        "gyro_x_saturation_count",
        "gyro_y_oor_count",
        "gyro_y_saturation_count",
        "gyro_z_oor_count",
        "gyro_z_saturation_count",
    ),
    [
        ("LeftAnkle_GYRO_x", 2, 2, 0, 0, 0, 0),
        ("LeftAnkle_GYRO_y", 0, 0, 2, 2, 0, 0),
        ("LeftAnkle_GYRO_z", 0, 0, 0, 0, 2, 2),
    ],
)
def test_imu_sensor_qc_over_gyro_limit(
    tmp_path,
    gyro_col,
    gyro_x_oor_count,
    gyro_x_saturation_count,
    gyro_y_oor_count,
    gyro_y_saturation_count,
    gyro_z_oor_count,
    gyro_z_saturation_count,
):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet"
    )
    make_synthetic_imu_parquet(filepath)

    con = duckdb.connect()
    try:
        con.execute(
            "CREATE TEMP TABLE imu_test AS SELECT * FROM read_parquet(?);",
            [str(filepath)],
        )

        con.execute(
            f"""
            UPDATE imu_test
            SET {gyro_col} = $value
            WHERE imu_latency = $timestamp
            """,
            {"value": 2000.1, "timestamp": 4.0},
        )

        con.execute(
            f"""
            UPDATE imu_test
            SET {gyro_col} = $value
            WHERE imu_latency = $timestamp
            """,
            {"value": -2000.1, "timestamp": 6.0},
        )

        con.execute(
            "COPY imu_test TO $output_path (FORMAT parquet)",
            {"output_path": str(filepath)},
        )
    finally:
        con.close()

    results = summarize_imu_sensor_qc(
        filepath, accel_saturation_threshold=15.5, gyro_saturation_threshold=1900
    )

    assert results[3]["sample_count"] == 200
    assert results[3]["null_count"] == 0
    assert results[3]["out_of_range_count"] == gyro_x_oor_count
    assert results[3]["saturation_count"] == gyro_x_saturation_count
    assert results[4]["sample_count"] == 200
    assert results[4]["null_count"] == 0
    assert results[4]["out_of_range_count"] == gyro_y_oor_count
    assert results[4]["saturation_count"] == gyro_y_saturation_count
    assert results[5]["sample_count"] == 200
    assert results[5]["null_count"] == 0
    assert results[5]["out_of_range_count"] == gyro_z_oor_count
    assert results[5]["saturation_count"] == gyro_z_saturation_count


@pytest.mark.parametrize("leg", ["Left", "Right"])
def test_summarize_imu_sensor_qc(tmp_path, leg):
    filepath = tmp_path / (
        f"sub-2000000001_ses-V02_task-{leg}LegMovement_tracksys-imu_acq-primary_motion.parquet"
    )
    make_synthetic_imu_parquet(filepath)
    output = summarize_imu_sensor_qc(
        filepath, accel_saturation_threshold=15.5, gyro_saturation_threshold=1900
    )

    assert len(output) == 6
    assert output[0]["column_name"] == f"{leg}Ankle_ACCEL_x"
    assert output[0]["sample_count"] == 200
    assert output[0]["null_count"] == 0
    assert output[0]["out_of_range_count"] == 0
    assert output[0]["saturation_count"] == 0
    assert output[1]["column_name"] == f"{leg}Ankle_ACCEL_y"
    assert output[1]["sample_count"] == 200
    assert output[1]["null_count"] == 0
    assert output[1]["out_of_range_count"] == 0
    assert output[1]["saturation_count"] == 0
    assert output[2]["column_name"] == f"{leg}Ankle_ACCEL_z"
    assert output[2]["sample_count"] == 200
    assert output[2]["null_count"] == 0
    assert output[2]["out_of_range_count"] == 0
    assert output[2]["saturation_count"] == 0
    assert output[3]["column_name"] == f"{leg}Ankle_GYRO_x"
    assert output[3]["sample_count"] == 200
    assert output[3]["null_count"] == 0
    assert output[3]["out_of_range_count"] == 0
    assert output[3]["saturation_count"] == 0
    assert output[4]["column_name"] == f"{leg}Ankle_GYRO_y"
    assert output[4]["sample_count"] == 200
    assert output[4]["null_count"] == 0
    assert output[4]["out_of_range_count"] == 0
    assert output[4]["saturation_count"] == 0
    assert output[5]["column_name"] == f"{leg}Ankle_GYRO_z"
    assert output[5]["sample_count"] == 200
    assert output[5]["null_count"] == 0
    assert output[5]["out_of_range_count"] == 0
    assert output[5]["saturation_count"] == 0


@pytest.mark.parametrize(
    ("accel_col", "x_null_count", "y_null_count"),
    [
        ("LeftAnkle_ACCEL_x", 1, 0),
        ("LeftAnkle_ACCEL_y", 0, 1),
    ],
)
def test_summarize_imu_sensor_qc_single_null(
    tmp_path, accel_col, x_null_count, y_null_count
):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet"
    )
    make_synthetic_imu_parquet(filepath)

    con = duckdb.connect()
    try:
        con.execute(
            "CREATE TEMP TABLE imu_test AS SELECT * FROM read_parquet(?);",
            [str(filepath)],
        )

        con.execute(
            f"""
            UPDATE imu_test
            SET {accel_col} = $value
            WHERE imu_latency = $timestamp
            """,
            {"value": None, "timestamp": 4.0},
        )

        con.execute(
            """
            UPDATE imu_test
            SET LeftAnkle_ACCEL_y = $value
            WHERE imu_latency = $timestamp
            """,
            {"value": 16.1, "timestamp": 6.0},
        )

        con.execute(
            "COPY imu_test TO $output_path (FORMAT parquet)",
            {"output_path": str(filepath)},
        )
    finally:
        con.close()

    output = summarize_imu_sensor_qc(
        filepath,
        accel_saturation_threshold=15.5,
        gyro_saturation_threshold=1900,
    )

    assert output[0]["sample_count"] == 200
    assert output[0]["null_count"] == x_null_count
    assert output[0]["out_of_range_count"] == 0
    assert output[0]["saturation_count"] == 0
    assert output[1]["sample_count"] == 200
    assert output[1]["null_count"] == y_null_count
    assert output[1]["out_of_range_count"] == 1
    assert output[1]["saturation_count"] == 1


def test_summarize_imu_sensor_qc_z_axis(tmp_path):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet"
    )
    make_synthetic_imu_parquet(filepath)

    con = duckdb.connect()
    try:
        con.execute(
            "CREATE TEMP TABLE imu_test AS SELECT * FROM read_parquet(?);",
            [str(filepath)],
        )

        con.execute(
            """
            UPDATE imu_test
            SET LeftAnkle_ACCEL_z = $value
            WHERE imu_latency = $timestamp
            """,
            {"value": None, "timestamp": 4.0},
        )

        con.execute(
            """
            UPDATE imu_test
            SET LeftAnkle_ACCEL_z = $value
            WHERE imu_latency = $timestamp
            """,
            {"value": -16.1, "timestamp": 6.0},
        )

        con.execute(
            "COPY imu_test TO $output_path (FORMAT parquet)",
            {"output_path": str(filepath)},
        )
    finally:
        con.close()

    output = summarize_imu_sensor_qc(
        filepath,
        accel_saturation_threshold=15.5,
        gyro_saturation_threshold=1900,
    )

    assert output[0]["sample_count"] == 200
    assert output[0]["null_count"] == 0
    assert output[0]["out_of_range_count"] == 0
    assert output[0]["saturation_count"] == 0
    assert output[1]["sample_count"] == 200
    assert output[1]["null_count"] == 0
    assert output[1]["out_of_range_count"] == 0
    assert output[1]["saturation_count"] == 0
    assert output[2]["sample_count"] == 200
    assert output[2]["null_count"] == 1
    assert output[2]["out_of_range_count"] == 1
    assert output[2]["saturation_count"] == 1


@pytest.mark.parametrize(
    (
        "gyro_col",
        "x_null_count",
        "y_null_count",
        "z_null_count",
        "x_oor_count",
        "y_oor_count",
        "z_oor_count",
        "x_saturation_count",
        "y_saturation_count",
        "z_saturation_count",
    ),
    [
        ("LeftAnkle_GYRO_x", 1, 0, 0, 1, 0, 0, 1, 0, 0),
        ("LeftAnkle_GYRO_y", 0, 1, 0, 0, 1, 0, 0, 1, 0),
        ("LeftAnkle_GYRO_z", 0, 0, 1, 0, 0, 1, 0, 0, 1),
    ],
)
def test_summarize_imu_sensor_qc_gyro_single_null(
    tmp_path,
    gyro_col,
    x_null_count,
    y_null_count,
    z_null_count,
    x_oor_count,
    y_oor_count,
    z_oor_count,
    x_saturation_count,
    y_saturation_count,
    z_saturation_count,
):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet"
    )
    make_synthetic_imu_parquet(filepath)

    con = duckdb.connect()
    try:
        con.execute(
            "CREATE TEMP TABLE imu_test AS SELECT * FROM read_parquet(?);",
            [str(filepath)],
        )

        con.execute(
            f"""
            UPDATE imu_test
            SET {gyro_col} = $value
            WHERE imu_latency = $timestamp
            """,
            {"value": None, "timestamp": 4.0},
        )

        con.execute(
            f"""
            UPDATE imu_test
            SET {gyro_col} = $value
            WHERE imu_latency = $timestamp
            """,
            {"value": 2000.1, "timestamp": 6.0},
        )

        con.execute(
            "COPY imu_test TO $output_path (FORMAT parquet)",
            {"output_path": str(filepath)},
        )
    finally:
        con.close()

    output = summarize_imu_sensor_qc(
        filepath,
        accel_saturation_threshold=15.5,
        gyro_saturation_threshold=1900,
    )

    assert output[3]["sample_count"] == 200
    assert output[3]["null_count"] == x_null_count
    assert output[3]["out_of_range_count"] == x_oor_count
    assert output[3]["saturation_count"] == x_saturation_count
    assert output[4]["sample_count"] == 200
    assert output[4]["null_count"] == y_null_count
    assert output[4]["out_of_range_count"] == y_oor_count
    assert output[4]["saturation_count"] == y_saturation_count
    assert output[5]["sample_count"] == 200
    assert output[5]["null_count"] == z_null_count
    assert output[5]["out_of_range_count"] == z_oor_count
    assert output[5]["saturation_count"] == z_saturation_count


def test_summarize_imu_sensor_qc_returns_zero_counts_for_empty_recording(tmp_path):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet"
    )
    make_synthetic_imu_parquet(filepath)

    con = duckdb.connect()
    try:
        con.execute(
            """
            CREATE TEMP TABLE empty_imu AS
            SELECT *
            FROM read_parquet(?)
            WHERE FALSE;
            """,
            [str(filepath)],
        )

        con.execute(
            "COPY empty_imu TO $output_path (FORMAT parquet)",
            {"output_path": str(filepath)},
        )
    finally:
        con.close()

    results = summarize_imu_sensor_qc(
        filepath, accel_saturation_threshold=15.5, gyro_saturation_threshold=1900
    )

    assert results[0] == {
        "column_name": "LeftAnkle_ACCEL_x",
        "sample_count": 0,
        "null_count": 0,
        "out_of_range_count": 0,
        "saturation_count": 0,
    }
    assert results[1] == {
        "column_name": "LeftAnkle_ACCEL_y",
        "sample_count": 0,
        "null_count": 0,
        "out_of_range_count": 0,
        "saturation_count": 0,
    }
    assert results[2] == {
        "column_name": "LeftAnkle_ACCEL_z",
        "sample_count": 0,
        "null_count": 0,
        "out_of_range_count": 0,
        "saturation_count": 0,
    }
    assert results[3] == {
        "column_name": "LeftAnkle_GYRO_x",
        "sample_count": 0,
        "null_count": 0,
        "out_of_range_count": 0,
        "saturation_count": 0,
    }
    assert results[4] == {
        "column_name": "LeftAnkle_GYRO_y",
        "sample_count": 0,
        "null_count": 0,
        "out_of_range_count": 0,
        "saturation_count": 0,
    }
    assert results[5] == {
        "column_name": "LeftAnkle_GYRO_z",
        "sample_count": 0,
        "null_count": 0,
        "out_of_range_count": 0,
        "saturation_count": 0,
    }


@pytest.mark.parametrize(
    "threshold",
    [0, -1, 16.1, float("nan"), float("inf"), float("-inf")],
)
def test_imu_sensor_qc_rejects_invalid_acceleration_threshold(tmp_path, threshold):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet"
    )
    make_synthetic_imu_parquet(filepath)

    with pytest.raises(ValueError, match="invalid threshold"):
        summarize_imu_sensor_qc(
            filepath,
            accel_saturation_threshold=threshold,
            gyro_saturation_threshold=1900,
        )


@pytest.mark.parametrize(
    "limit",
    [0, -1, float("nan"), float("inf"), float("-inf")],
)
def test_imu_sensor_qc_rejects_invalid_acceleration_limit(tmp_path, limit):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet"
    )
    make_synthetic_imu_parquet(filepath)

    with pytest.raises(ValueError, match="invalid threshold"):
        summarize_imu_sensor_qc(
            filepath,
            accel_saturation_threshold=15.5,
            gyro_saturation_threshold=1900,
            accel_measurement_limit=limit,
        )


@pytest.mark.parametrize(
    "threshold",
    [0, -1, 2000.1, -2100.1, float("nan"), float("inf"), float("-inf")],
)
def test_imu_sensor_qc_rejects_invalid_gyro_threshold(tmp_path, threshold):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet"
    )
    make_synthetic_imu_parquet(filepath)

    with pytest.raises(ValueError, match="invalid threshold"):
        summarize_imu_sensor_qc(
            filepath,
            accel_saturation_threshold=15.5,
            gyro_saturation_threshold=threshold,
        )


@pytest.mark.parametrize(
    "limit",
    [0, -1, float("nan"), float("inf"), float("-inf")],
)
def test_imu_sensor_qc_rejects_invalid_gyro_limit(tmp_path, limit):
    filepath = (
        tmp_path
        / "sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.parquet"
    )
    make_synthetic_imu_parquet(filepath)

    with pytest.raises(ValueError, match="invalid threshold"):
        summarize_imu_sensor_qc(
            filepath,
            accel_saturation_threshold=15.5,
            gyro_saturation_threshold=1900,
            gyro_measurement_limit=limit,
        )
