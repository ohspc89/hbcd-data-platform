# HBCD Data Platform

A Python-based data engineering project for ingesting, cataloging, and validating metadata from BIDS-style infant wearable sensor datasets.

The project demonstrates reproducible data ingestion, metadata quality control, transactional persistence, and automated testing using Python, DuckDB, pytest, and GitHub Actions.

**Status:** Work in progress

## Motivation

Large-scale wearable sensor studies produce thousands of files across participants, recording sessions, and data modalities. Managing these files reliably requires more than organizing directories: a data platform must track file metadata, detect missing or inconsistent records, and preserve data integrity when processing fails.

This project addresses these challenges through a lightweight, testable metadata pipeline inspired by the Healthy Brain and Child Development (HBCD) Study.

The current implementation focuses on file discovery and metadata validation. Raw sensor time-series processing and analytical data models are planned for future development.

**Data privacy:** Real HBCD participant data is not distributed with this repository. Automated tests use synthetic fixtures.

## Features

- File discovery: Recursively scans BIDS-style directory structures and extracts metadata from filenames, including participant IDs, session IDs, and acquisition parameters.
- Idempotent ingestion: Loads file metadata into DuckDB using upserts, preventing duplicate records and updating existing entries across repeated scans.
- Metadata validation: Checks for required participant-level `_sessions.tsv` and session-level `_scans.tsv` files, producing standardized PASS/FAIL
- Transactional persistence: Atomically replaces QC results using database transactions, rolling back changes if an error occurs during persistence.

## Architecture

BIDS-style file system
         │
         ▼
    File scanner
         │
         ▼
  DuckDB file_manifest
         │
         ▼
  Metadata validation
         │
         ▼
 DuckDB validation_results

**Design decision — Separating metadata from raw sensor data**

The platform stores file metadata and validation results in DuckDB while keeping raw sensor time-series in file-based storage. This separation enables efficient file discovery, filtering, and quality control without repeatedly loading large sensor datasets. Downstream processing pipelines can use the manifest to locate and selectively read relevant files.

## Quick Start

### Prerequisites

- Python 3.12 or later (Python 3.12 is the currently tested version)
- [uv](https://docs.astral.sh/uv/) for Python dependency management
- Git

### Installation

Clone the repository:

```bash
git clone git@github.com:ohspc89/hbcd-data-platform.git
cd hbcd-data-platform
```

Install project dependencies:

```bash
uv sync --locked
```

### Run Tests

Execute the automated test suite:

```bash
uv run pytest -q
```

Tests use synthetic BIDS-style fixtures and temporary DuckDB databases. Access to the original HBCD dataset is not required.

### Continuous Integration

GitHub Actions automatically runs the test suite on pushes and pull requests targeting the `main` branch.

The CI workflow is defined in `.github/workflows/tests.yml`.
