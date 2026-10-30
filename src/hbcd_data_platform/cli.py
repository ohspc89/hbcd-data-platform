import argparse
import logging
from pathlib import Path
import sys

import duckdb

from hbcd_data_platform.config import PipelineConfig, validate_pipeline_config
from hbcd_data_platform.load_manifest import load_manifest
from hbcd_data_platform.orchestration import run_imu_processing
from hbcd_data_platform.pipeline import run_pipeline
from hbcd_data_platform.validate_manifest import save_validation_results


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="HBCD metadata ingestion pipeline")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ingest
    ingest_parser = subparsers.add_parser(
        "ingest", help="Scan files and update the DuckDB manifest"
    )
    ingest_parser.add_argument(
        "--raw-path",
        required=True,
        type=Path,
        help="Directory containing BIDS-style data",
    )
    ingest_parser.add_argument(
        "--db-path", required=True, type=Path, help="Path to the DuckDB database file"
    )

    # validate
    validate_parser = subparsers.add_parser(
        "validate", help="Save validated scanned files"
    )

    validate_parser.add_argument(
        "--db-path", required=True, help="Path to the DuckDB database file"
    )

    # run
    run_parser = subparsers.add_parser(
        "run", help="HBCD metadata ingestion and validation pipeline"
    )

    run_parser.add_argument(
        "--raw-path",
        required=True,
        type=Path,
        help="Directory containing BIDS-style data",
    )
    run_parser.add_argument(
        "--db-path", required=True, type=Path, help="Path to the DuckDB database file"
    )

    # process
    process_parser = subparsers.add_parser(
        "process-imu", help="parquet file processing pipeline"
    )
    process_parser.add_argument(
        "--raw-path",
        required=True,
        type=Path,
        help="Directory containing BIDS-style data",
    )
    process_parser.add_argument(
        "--db-path", required=True, type=Path, help="Path to the DuckDB database file"
    )
    process_parser.add_argument(
        "--window-seconds",
        type=float,
        default=2.0,
        help="processing window duration in seconds (default: 2.0)",
    )

    args = parser.parse_args()

    if args.command == "ingest":
        config = PipelineConfig(raw_path=args.raw_path, db_path=args.db_path)
        validate_pipeline_config(config)
        load_manifest(args.raw_path, args.db_path)

    elif args.command == "validate":
        if not Path(args.db_path).is_file():
            raise FileNotFoundError(f"Database file not found: '{args.db_path}'")

        con = duckdb.connect(args.db_path)
        try:
            save_validation_results(con)
        finally:
            con.close()

    elif args.command == "run":
        run_pipeline(PipelineConfig(raw_path=args.raw_path, db_path=args.db_path))

    elif args.command == "process-imu":
        if not Path(args.db_path).is_file():
            raise FileNotFoundError(f"Database file not found: '{args.db_path}'")
        con = duckdb.connect(args.db_path)
        try:
            manifest_exists = con.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'main'
                    AND table_name = 'file_manifest'
                );
                """
            ).fetchone()[0]
            if not manifest_exists:
                raise ValueError(
                    "The table 'file_manifest' is not found in the database."
                )
            result = run_imu_processing(con, args.raw_path, args.window_seconds)
            print("IMU Processing Summary")
            print("----------------------")
            for key, value in result.items():
                print(f"{key.capitalize():<10}: {value}")

            return 1 if result["failed"] > 0 else 0

        finally:
            con.close()


if __name__ == "__main__":
    sys.exit(main())
