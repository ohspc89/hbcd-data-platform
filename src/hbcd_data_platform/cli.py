import argparse
import logging
from pathlib import Path

import duckdb
from hbcd_data_platform.load_manifest import load_manifest
from hbcd_data_platform.validate_manifest import save_validation_results
from hbcd_data_platform.pipeline import run_pipeline


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
        "--raw-path", required=True, help="Directory containing BIDS-style data"
    )
    ingest_parser.add_argument(
        "--db-path", required=True, help="Path to the DuckDB database file"
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
        "--raw-path", required=True, help="Directory containing BIDS-style data"
    )
    run_parser.add_argument(
        "--db-path", required=True, help="Path to the DuckDB database file"
    )

    args = parser.parse_args()

    if args.command == "ingest":
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
        run_pipeline(args.raw_path, args.db_path)


if __name__ == "__main__":
    main()
