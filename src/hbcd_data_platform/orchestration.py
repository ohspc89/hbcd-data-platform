import logging
from pathlib import Path

import duckdb
import pandas as pd

import hbcd_data_platform.imu as imu_module

logger = logging.getLogger(__name__)


def run_imu_processing(
    con: duckdb.DuckDBPyConnection,
    raw_path: Path,
    window_seconds: float = 2.0,
) -> dict[str, int]:
    """Process new or modified IMU files and store window-level summaries.

    Files are selected by comparing file_manifest with imu_processing_status.
    A file is selected if any of the following conditions is met:
      - It has no processing status.
      - Its size_bytes has changed since the last successful processing.
      - Its modified_at has changed since the last successful processing.
      - Its processing window duration differs from the previously used value.

    Only IMU motion Parquet files are eligible for processing.
    Present files are going to be processed.

    Individual file failures are logged without stopping the remaining files.

    Args:
        con: DuckDB connection containing the file_manifest table.
        raw_path: Root directory containing the source files.
        window_seconds: Duration of each summary window in seconds.
    """

    imu_module.create_imu_window_summary_table(con)

    imu_module.create_imu_processing_status_table(con)

    eligible = con.execute(
        """
        SELECT COUNT(*)
        FROM file_manifest
        WHERE tracking_system = 'imu'
        AND acquisition = 'primary'
        AND suffix = 'motion'
        AND extension = '.parquet'
        AND is_present = TRUE
        """
    ).fetchone()[0]

    files_to_process = con.execute(
        """
        SELECT f.file_id, f.relative_path
        FROM file_manifest f
        LEFT JOIN imu_processing_status i
        ON f.file_id = i.file_id
        WHERE (i.file_id IS NULL
               OR i.processed_size_bytes IS DISTINCT FROM f.size_bytes
               OR i.processed_modified_at IS DISTINCT FROM f.modified_at
               OR i.window_seconds IS DISTINCT FROM ?)
        AND f.tracking_system = 'imu'
        AND f.acquisition = 'primary'
        AND f.suffix = 'motion'
        AND f.extension = '.parquet'
        AND f.is_present = TRUE
        """,
        [window_seconds],
    ).fetchall()

    skipped = eligible - len(files_to_process)

    processed = 0
    failed = 0
    for file_id, relative_path in files_to_process:
        try:
            if (raw_path / relative_path).is_file():
                process_imu_file(con, file_id, raw_path, window_seconds)
                processed += 1
            else:
                logger.warning("File not exists=%s", relative_path)
                failed += 1
        except Exception:
            logger.exception("Failed to process file_id=%s", file_id)
            failed += 1

    return {
        "eligible":eligible,
        "skipped": skipped,
        "processed": processed,
        "failed": failed
    }


def process_imu_file(
    con: duckdb.DuckDBPyConnection,
    file_id: int,
    raw_path: Path,
    window_seconds: float = 2.0,
) -> None:
    """Summarize IMU data for a single file and store the results.

    Looks up the file in the manifest, computes window-level IMU
    statistics, and replaces any existing summaries for that file.

    Args:
        con: DuckDB connection containing the file_manifest,
            imu_window_summary, and imu_processing_status tables.
        file_id: Identifier of the file in file_manifest.
        raw_path: Root directory containing the source files.
        window_seconds: Duration of each summary window in seconds.

    Raises:
        ValueError: If file_id does not exist in file_manifest.
        FileNotFoundError: If the source file does not exist.
    """
    row = con.execute(
        """
        SELECT relative_path, size_bytes, modified_at
        FROM file_manifest
        WHERE file_id = ?
        """,
        [file_id],
    ).fetchone()

    if row is None:
        raise ValueError(f"Invalid file id: '{file_id}'")

    file_path = raw_path / row[0]
    if not file_path.exists():
        raise FileNotFoundError(f"File Not Exists: '{file_path}'")

    before = file_path.stat()
    modified_at = (
        pd.to_datetime(before.st_mtime, unit="s").as_unit("us").to_pydatetime()
    )
    if modified_at != row[2] or before.st_size != row[1]:
        raise ValueError(f"File changed before processing: '{file_path}'")

    summaries = imu_module.summarize_imu_windows(
        file_path, window_seconds=window_seconds
    )

    after = file_path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError(f"File changed during processing: '{file_path}'")

    # Returns None
    imu_module.replace_imu_window_summaries(con, file_id, summaries, window_seconds)
