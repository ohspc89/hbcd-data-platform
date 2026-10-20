from pathlib import Path

import duckdb

import hbcd_data_platform.imu as imu_module


def process_imu_file(
    con: duckdb.DuckDBPyConnection,
    file_id: int,
    raw_path: Path,
    window_seconds: float = 2.0,
) -> None:
    row = con.execute(
        "SELECT relative_path FROM file_manifest WHERE file_id = ?",
        [file_id],
    ).fetchone()

    if row is None:
        raise ValueError(f"Invalid file id: '{file_id}'")

    file_path = raw_path / row[0]
    if not file_path.exists():
        raise FileNotFoundError(f"File Not Exists: '{file_path}'")

    summaries = imu_module.summarize_imu_windows(
        file_path, window_seconds=window_seconds
    )

    # Returns None
    imu_module.create_imu_window_summary_table(con)

    # Returns None
    imu_module.replace_imu_window_summaries(con, file_id, summaries)
