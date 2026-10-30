# HBCD Data Platform - Architecture

## Entry points

The CLI provides metadata ingestion (`ingest`), metadata validation (`validate`), and both steps together (`run`). IMU processing is available through the Python API and is not yet called by the CLI or `run_pipeline()`.

## Processing flow

1. `load_manifest()` scans raw files and upserts `file_manifest`, preserving file identity and discovery history. Files absent from the latest scan are marked `is_present = FALSE`.
2. `run_imu_processing()` selects IMU motion Parquet files with no processing status or a changed file size, modification time, or requested window duration.
3. Missing source files are skipped while their previous summaries and processing status remain available.
4. `process_imu_file()` verifies source size and modification time against the manifest before computing window summaries.
5. After summarization, it checks source size and nanosecond modification time again. Detected changes raise an exception before results are saved.
6. `replace_imu_window_summaries()` replaces the file's summaries and updates its processing status in one transaction. Persistence failures roll back both changes.
7. The orchestrator logs individual file failures and continues with other files. Unchanged files with the same window duration are skipped on subsequent runs.

## Function map

| Function | Input | Output or side effect | Called by |
| --- | --- | --- | --- |
| `load_manifest()` | Raw path, DB path, optional scan time | Updates `file_manifest` | CLI ingestion and pipeline runner; Python callers |
| `save_validation_results()` | Connection | Replaces metadata validation results | CLI validation and pipeline runner |
| `summarize_imu_windows()` | Parquet path, window duration | List of window summaries | `process_imu_file()` |
| `replace_imu_window_summaries()` | Connection, file ID, summaries, window duration | Atomically updates summaries and processing status | `process_imu_file()` |
| `process_imu_file()` | Connection, file ID, raw path, window duration | Checks source stability and processes one file | `run_imu_processing()` |
| `run_imu_processing()` | Connection, raw path, window duration | Selects and processes eligible files | Python callers; CLI integration planned |

## Database tables

### `file_manifest`

One row per relative path ever discovered, with a stable `file_id`. Metadata reflects the most recent scan in which the file was found. `discovered_at` is retained across scans; `last_seen_at` changes when a file is observed again.

`is_present` reflects the latest scan. It does not guarantee that the file still exists at processing time, so orchestration also checks the filesystem. Missing files retain their manifest records and related IMU results.

### `validation_results`

Stores participant-level sessions-file and session-level scans-file existence checks, including PASS/FAIL, observed and expected counts, and validation time. Only present files satisfy the checks; historical participant/session identities remain in the validation pool. Each validation run replaces the previous results transactionally.

### `imu_window_summary`

One row per `(file_id, window_index)`, with window boundaries, sample counts, valid sensor counts, and magnitude variances. A successful replacement retains the latest results for one window duration per file. Different durations are not stored concurrently.

### `imu_processing_status`

One row per successfully processed file. Stores processing time, processed file size and modification time, and `window_seconds`. These values determine whether the file needs reprocessing.

Existing tables without `window_seconds` gain the column automatically. Existing rows initially have a NULL duration, which makes them eligible for reprocessing.

## Change detection and recovery

The manifest stores modification times at microsecond precision. The pre-processing check uses the same conversion as ingestion; the before/after summarization check compares filesystem nanosecond timestamps directly.

Change detection uses file metadata rather than content hashes. Content changes that preserve both size and modification time are outside this check's scope. Files should be stable while being processed.

After a detected source change, rescan and rerun processing once the source is stable. If a missing file reappears, ingestion updates its presence and metadata while preserving its ID. It is reprocessed if its size, modification time, or requested window duration differs from the last successful processing.

IMU schema, timestamp, and sensor QC functions are separate Python APIs. The window-processing orchestrator does not automatically run those QC checks.
