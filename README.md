# HBCD Data Platform

A Python and DuckDB data engineering portfolio project for discovering, validating, and summarizing BIDS-style infant wearable-sensor data. Inspired by the data-management challenges of the Healthy Brain and Child Development (HBCD) Study.

**Status:** Work in progress. Metadata ingestion and validation are available through a CLI. IMU time-series QC, window summaries, and manifest-driven incremental processing are implemented as Python APIs. IMU processing is not yet connected to the CLI.

## Problem and approach

Large-scale wearable studies produce thousands of participant/session files and large sensor recordings. Reliable analysis requires an auditable file inventory, explicit data-quality rules, and safe reruns after files change or processing fails.

This project keeps raw time-series files on disk and stores file metadata and quality-control results in DuckDB. Its engineering focus is **SQL transformations, idempotent ingestion, transactional persistence, and automated tests**.

## Implemented capabilities

| Component | Functionality |
| --- | --- |
| File discovery | Recursively scan BIDS-style paths and parse participant, session, task, tracking-system, acquisition, and suffix metadata. |
| Manifest ingestion | Upsert by unique relative path, preserve file identity and discovery history, update last-seen timestamps, and track missing files with `is_present` without deleting their records. |
| Metadata validation | Check participant-level `_sessions.tsv` and session-level `_scans.tsv` files; persist PASS/FAIL results. |
| IMU timestamp QC | Summarize TSV sampling intervals and check expected frequency against a configurable tolerance. |
| IMU schema QC | Check expected left/right ankle accelerometer and gyroscope columns in TSV files. |
| IMU sensor QC | Calculate per-axis NaN, null, out-of-range, and saturation counts from Parquet recordings. |
| IMU window summaries | Compute window-level sample counts and population variance of acceleration/gyroscope magnitudes from Parquet. |
| Incremental IMU processing | Process new files and reprocess when scanned file size, modification time, or requested window duration changes. Preserve summaries for missing files. |
| Source-change detection | Check source metadata against the manifest before summarizing and check for changes during summarization before saving results. |
| Transactional persistence | Roll back failed manifest, metadata-validation, or IMU-window-summary replacements. |
| Automated testing | Exercise synthetic data and failure cases using pytest, temporary DuckDB databases, and GitHub Actions. |

## Architecture

```text
BIDS-style directory
    |
    v
Scanner / filename parser
    |
    v
DuckDB: file_manifest ---> metadata validation ---> validation_results

Python API: run_imu_processing()
    |
    +--- file_manifest + imu_processing_status: select files
    |
    v
Parquet IMU file ---> summarize_imu_windows()
                              |
                              v
                 replace_imu_window_summaries()
                              |
                              v
             imu_window_summary + imu_processing_status
                      (one transaction)
```

Manifest-driven IMU orchestration is available through the Python API. The CLI `run` command currently performs metadata ingestion and validation only. See [architecture details](docs/architecture.md).

### Data model

- `file_manifest`: one row per relative path ever discovered; stable `file_id`, parsed filename metadata, discovery and last-seen timestamps, and `is_present` from the latest scan.
- `validation_results`: participant/session checks, rule, status, observed/expected counts, and validation timestamp.
- `imu_window_summary`: one row per `(file_id, window_index)` with counts and magnitude variances; foreign key to `file_manifest`.
- `imu_processing_status`: one row per successfully processed file; processing time, processed file size and modification time, and window duration. Each successful run replaces that file's previous summaries and status together.

## Getting started

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Git.

```bash
git clone https://github.com/ohspc89/hbcd-data-platform.git
cd hbcd-data-platform
uv sync --locked
uv run pytest -q
```

To run metadata ingestion and validation against a **BIDS-style directory you control**, keeping the database **outside** the raw-data directory:

```bash
uv run hbcd-data-platform run \
  --raw-path /path/to/bids-data \
  --db-path /path/to/platform.duckdb
```

The CLI also exposes `ingest` (same two arguments) and `validate --db-path /path/to/platform.duckdb` (against an existing database).

IMU functions are in `src/hbcd_data_platform/imu.py`, including `summarize_imu_windows()`, `create_imu_window_summary_table()`, and `replace_imu_window_summaries()`.

To run incremental IMU processing through Python after scanning the source directory:

```python
from pathlib import Path

import duckdb

from hbcd_data_platform.load_manifest import load_manifest
from hbcd_data_platform.orchestration import run_imu_processing

raw_path = Path("/path/to/bids-data")
db_path = Path("/path/to/platform.duckdb")

load_manifest(raw_path, db_path)
with duckdb.connect(db_path) as con:
    run_imu_processing(con, raw_path, window_seconds=2.0)
```

Only manifest entries with `tracking_system='imu'`, `suffix='motion'`, and `extension='.parquet'` are selected. Window summaries support the left/right leg movement tasks. Individual file failures are logged while processing continues for other files; a failed file's previous summaries and processing status remain unchanged. After a detected source change, rescan and rerun processing once the source is stable.

Change detection uses file size and modification time rather than content hashes. Existing processing-status tables gain the window-duration column automatically; rows with an unknown duration are selected for reprocessing.

## Tests and privacy

```bash
uv run pytest -q
```

Tests cover valid and invalid metadata, timestamp anomalies, sensor NaN/null counts, window boundaries, incremental reruns, changed window durations, missing and reappearing files, processing-status schema migration, source changes before and during processing, and transaction rollback. GitHub Actions runs pytest on pushes and pull requests to `main`.

**No real HBCD participant recordings or identifiable participant data are distributed with this repository.** Tests use synthetic fixtures.

## Next engineering milestones

1. **CLI integration:** Add manifest-driven IMU processing to the CLI.
2. **Run reporting:** Report processed, skipped, and failed files with a run-level summary.
3. **Performance:** Measure scan and IMU-processing performance on larger synthetic workloads.

This is a portfolio and learning project, **not a deployed clinical system**. Production AWS, Snowflake, HL7/FHIR, and HIPAA-compliant infrastructure are not claimed.
