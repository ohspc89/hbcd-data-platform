import pandas as pd
import pytest

from conftest import make_synthetic_imu_tsv
from hbcd_data_platform.imu import summarize_imu_timestamps, validate_imu_timestamps

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
    fname = (
        "sub-0001_ses-V02_"
        "tracksys-imu_acq-primary_motion.tsv"
    )
    with pytest.raises(ValueError):
        make_synthetic_imu_tsv(tmp_path / fname)


def test_filename_with_invalid_task_raises_value_error(tmp_path):
    fname = (
        "sub-0001_ses-V02_task-SquidLegMovement_"
        "tracksys-imu_acq-primary_motion.tsv"
    )
    with pytest.raises(ValueError):
        make_synthetic_imu_tsv(tmp_path / fname)


def test_summarize_imu_timestamps_returns_expected_values(tmp_path):
    fname = (
        f"sub-0001_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.tsv"
        )
    make_synthetic_imu_tsv(tmp_path / fname)

    out = summarize_imu_timestamps(tmp_path / fname)
    assert out["sample_count"] == 200
    assert out["start_s"] == pytest.approx(0.0)
    assert out["end_s"] == pytest.approx(7.96)
    assert out["min_interval_s"] == pytest.approx(0.04)
    assert out["max_interval_s"] == pytest.approx(0.04)


def test_file_with_header_only_raises_value_error(tmp_path):
    fname = (
        "sub-0001_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.tsv"
    )
    fpath = tmp_path / fname
    fpath.write_text(
        "imu_latency\tLeftAnkle_ACCEL_x\tLeftAnkle_ACCEL_y\tLeftAnkle_ACCEL_z\tLeftAnkle_GYRO_x\tLeftAnkle_GYRO_y\tLeftAnkle_GYRO_z\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="contains no samples"):
        summarize_imu_timestamps(fpath)


def test_normal_sampling_hz(tmp_path):
    fname = (
        f"sub-0001_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.tsv"
        )
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    validation = validate_imu_timestamps(fpath)
    assert validation["status"] == "PASS"


def test_timestamp_summary_detects_missing_sample(tmp_path):
    fname = (
        f"sub-0001_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.tsv"
        )
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
    fname = (
        f"sub-0001_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.tsv"
        )
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
    fname = (
        f"sub-0001_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.tsv"
        )
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
    fname = (
        f"sub-0001_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.tsv"
        )
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
    fname = (
        f"sub-0001_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.tsv"
        )
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
    fname = (
        f"sub-0001_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.tsv"
        )
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    validation = validate_imu_timestamps(fpath, expected_hz=50)
    assert validation["status"] == "FAIL"


@pytest.mark.parametrize("expected_hz", [0, -25])
def test_invalid_expected_frequency_raises_value_error(tmp_path, expected_hz):
    fname = (
        f"sub-0001_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.tsv"
        )
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    with pytest.raises(ValueError, match="greater than zero"):
        validate_imu_timestamps(fpath, expected_hz=expected_hz)


@pytest.mark.parametrize(
    ("offset_s", "expected_status"),
    [(0.0000005, "PASS"), (0.0000020, "FAIL"),],
)
def test_timestamp_tolerance_controls_validation_status(tmp_path, offset_s, expected_status):
    fname = (
        f"sub-0001_ses-V02_task-LeftLegMovement"
        "_tracksys-imu_acq-primary_motion.tsv"
        )
    fpath = tmp_path / fname
    make_synthetic_imu_tsv(fpath)

    df = pd.read_csv(fpath, sep="\t")
    df.at[42, "imu_latency"] = df.at[42, "imu_latency"] + offset_s
    df.to_csv(fpath, sep="\t", index=False)

    validation = validate_imu_timestamps(fpath)
    assert validation["status"] == expected_status
    assert validation["max_interval_s"] == pytest.approx(0.04 + offset_s)
    assert validation["min_interval_s"] == pytest.approx(0.04 - offset_s)
