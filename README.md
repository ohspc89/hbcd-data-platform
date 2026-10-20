# HBCD Data Platform

A Python and DuckDB data engineering portfolio project for discovering, validating, and summarizing BIDS-style infant wearable-sensor data. Inspired by the data-management challenges of the Healthy Brain and Child Development (HBCD) Study.

**Status:** Work in progress. Metadata ingestion and validation are available through a CLI. IMU time-series QC and window-summary functions are implemented as Python APIs but are not yet connected to the end-to-end CLI.

## Problem and approach

Large-scale wearable studies produce thousands of participant/session files and large sensor recordings. Reliable analysis requires an auditable file inventory, explicit data-quality rules, and safe reruns after files change or processing fails.

This project keeps raw time-series files on disk and stores file metadata and quality-control results in DuckDB. Its engineering focus is **SQL transformations, idempotent ingestion, transactional persistence, and automated tests**.

## Implemented capabilities

| Component | Functionality |
| --- | --- |
| File discovery | Recursively scan BIDS-style paths and parse participant, session, task, tracking-system, acquisition, and suffix metadata. |
| Manifest ingestion | Upsert by unique relative path, retain first-discovered timestamps, update last-seen timestamps, and delete missing manifest entries. |
| Metadata validation | Check participant-level `_sessions.tsv` and session-level `_scans.tsv` files; persist PASS/FAIL results. |
| IMU timestamp QC | Summarize TSV sampling intervals and check expected frequency against a configurable tolerance. |
| IMU schema QC | Check expected left/right ankle accelerometer and gyroscope columns in TSV files. |
| IMU sensor QC | Calculate per-axis null, out-of-range, and saturation counts from Parquet recordings. |
| IMU window summaries | Compute window-level sample counts and population variance of acceleration/gyroscope magnitudes from Parquet. |
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

Parquet IMU file ---> summarize_imu_windows() ---> window summaries
                                                        |
                                                        v
                                             imu_window_summary
```

The IMU-processing functions currently operate independently. **Manifest-driven IMU orchestration is not yet implemented.**

### Data model

- `file_manifest`: one row per relative path; stable `file_id`, parsed filename metadata, discovery and last-seen timestamps.
- `validation_results`: participant/session checks, rule, status, observed/expected counts, and validation timestamp.
- `imu_window_summary`: one row per `(file_id, window_index)` with counts and magnitude variances; foreign key to `file_manifest`.

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

## Tests and privacy

```bash
uv run pytest -q
```

Tests cover valid and invalid metadata, timestamp anomalies, malformed sensor data, window boundaries, persistence reruns, and transaction rollback. GitHub Actions runs pytest on pushes and pull requests to `main`.

**No real HBCD participant recordings or identifiable participant data are distributed with this repository.** Tests use synthetic fixtures.

## Next engineering milestones

1. **Manifest-driven IMU processing:** Resolve a Parquet file from its manifest record, summarize its windows, and persist by `file_id` without duplicates on rerun.
2. **Referential integrity:** Handle manifest deletions without leaving orphaned IMU summaries or triggering foreign-key failures.
3. **Operationalization:** Add IMU processing to the CLI, structured run-level logs, failure recovery, and performance measurements on synthetic workloads.

This is a portfolio and learning project, **not a deployed clinical system**. Production AWS, Snowflake, HL7/FHIR, and HIPAA-compliant infrastructure are not claimed.
