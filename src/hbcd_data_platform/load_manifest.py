import argparse
import pandas as pd
import duckdb
from hbcd_data_platform.scan_files import scan_files


def load_manifest(raw_path, db_path, scan_time=None):
    """
    connect to DB, create sequence & table, scan,
    DataFrame transform, upsert, and connection close

    Parameters
    ----------
    raw_path: Path
        path to rawdata
    db_path: Path
        path to DB

    Returns
    -------
    None
    """
    con = duckdb.connect(db_path)

    try:
        con.sql("CREATE SEQUENCE IF NOT EXISTS file_id_sequence START 1")
        con.sql(
            """
            CREATE TABLE IF NOT EXISTS file_manifest (
                file_id BIGINT DEFAULT nextval('file_id_sequence') PRIMARY KEY,
                filename VARCHAR,
                relative_path VARCHAR UNIQUE,
                extension VARCHAR,
                size_bytes BIGINT,
                modified_at TIMESTAMP,
                participant_id VARCHAR,
                session_id VARCHAR,
                task VARCHAR,
                tracking_system VARCHAR,
                acquisition VARCHAR,
                suffix VARCHAR,
                discovered_at TIMESTAMP NOT NULL,
                last_seen_at TIMESTAMP NOT NULL,
            )
            """
        )

        records = scan_files(raw_path)

        expected_columns = [
            "filename",
            "relative_path",
            "extension",
            "size_bytes",
            "modified_at",
            "participant_id",
            "session_id",
            "task",
            "tracking_system",
            "acquisition",
            "suffix",
            "discovered_at",
            "last_seen_at",
        ]
        df = pd.DataFrame(records)
        df.rename(
            columns={
                "sub": "participant_id",
                "ses": "session_id",
                "tracksys": "tracking_system",
                "acq": "acquisition",
                "modified_time": "modified_at",
            },
            inplace=True,
        )

        for expected in expected_columns:
            if not expected in df:
                df[expected] = pd.NA

        df["modified_at"] = pd.to_datetime(df["modified_at"], unit="s")
        df["modified_at"] = df["modified_at"].astype("datetime64[us]")
        if scan_time is None:
            scan_time = pd.Timestamp.now("UTC").tz_localize(None)
        df["discovered_at"] = scan_time
        df["last_seen_at"] = scan_time

        con.sql(
            """
            INSERT INTO file_manifest (
                filename,
                relative_path,
                extension,
                size_bytes,
                modified_at,
                participant_id,
                session_id,
                task,
                tracking_system,
                acquisition,
                suffix,
                discovered_at,
                last_seen_at
            )
            SELECT
                filename,
                relative_path,
                extension,
                size_bytes,
                modified_at,
                participant_id,
                session_id,
                task,
                tracking_system,
                acquisition,
                suffix,
                discovered_at,
                last_seen_at
            FROM df
            ON CONFLICT (relative_path)
            DO UPDATE SET
                filename = excluded.filename,
                extension = excluded.extension,
                size_bytes = excluded.size_bytes,
                modified_at = excluded.modified_at,
                participant_id = excluded.participant_id,
                session_id = excluded.session_id,
                task = excluded.task,
                tracking_system = excluded.tracking_system,
                acquisition = excluded.acquisition,
                suffix = excluded.suffix,
                last_seen_at = excluded.last_seen_at;
            """
        )
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to HBCD raw BIDS directory")
    parser.add_argument(
        "--db",
        default="hbcd.duckdb",
        help="Path to DuckDB database",
    )

    args = parser.parse_args()

    load_manifest(args.path, args.db)
