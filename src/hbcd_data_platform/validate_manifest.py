import duckdb


def insert_validation_results(con, relation):
    con.sql("INSERT INTO validation_results SELECT * FROM relation;")


def validate_participant_sessions(con):
    """
    Validate whether every participant in the file manifest
    has a participant-level sessions.tsv file.

    Parameters
    ----------
    con
        An open DuckDB connection containing the file_manifest table.

    PASS
        The participant has a row where sessions_count = 1.

    FAIL
        The participant has no row where sessions_count = 0.
    """
    return con.sql(
        """
        WITH pool AS (
            SELECT DISTINCT participant_id
            FROM file_manifest
            WHERE participant_id IS NOT NULL
        ), subset AS (
            SELECT participant_id, suffix, extension
            FROM file_manifest
            WHERE extension = '.tsv' AND suffix = 'sessions' AND session_id IS NULL
        ), session_validation AS (
            SELECT
                p.participant_id,
                COUNT(s.suffix) AS sessions_count
            FROM pool p
            LEFT JOIN subset s
              ON p.participant_id = s.participant_id
            GROUP BY p.participant_id
        )
        SELECT
            participant_id,
            CAST(NULL AS VARCHAR) AS session_id,
            'participant_sessions' AS rule,
            CASE
              WHEN sessions_count = 1 THEN 'PASS'
              ELSE 'FAIL'
            END AS status,
            sessions_count AS observed,
            CAST(1 AS BIGINT) AS expected
        FROM session_validation;
        """
    )


def validate_session_scans(con):
    """
    Validate whether every participant in the file manifest
    has a session-level scans.tsv file.

    Parameters
    ----------
    con
        An open DuckDB connection containing the file_manifest table.

    PASS
        The participant has a row per session with scans_count = 1.

    FAIL
        The participant has a row per session where scans_count = 0.
    """
    return con.sql(
        """
        WITH pool AS (
            SELECT DISTINCT
                participant_id,
                session_id
            FROM file_manifest
            WHERE participant_id IS NOT NULL AND session_id IS NOT NULL
        ), subset AS (
            SELECT participant_id, session_id, suffix, extension
            FROM file_manifest
            WHERE extension = '.tsv' AND suffix = 'scans' AND session_id IS NOT NULL
        ), scans_validation AS (
            SELECT
                p.participant_id,
                p.session_id,
                COUNT(s.suffix) AS scans_count
            FROM pool p
            LEFT JOIN subset s
              ON p.participant_id = s.participant_id
              AND p.session_id = s.session_id
            GROUP BY p.participant_id, p.session_id
        )
        SELECT
            participant_id,
            session_id,
            'session_scans' AS rule,
            CASE
              WHEN scans_count = 1 THEN 'PASS'
              ELSE 'FAIL'
            END AS status,
            scans_count AS observed,
            CAST(1 AS BIGINT) AS expected
        FROM scans_validation;
        """
    )


def save_validation_results(con):
    participant_results = validate_participant_sessions(con)
    session_results = validate_session_scans(con)

    combined = participant_results.union(session_results)
    combined.aggregate("rule, status, COUNT(*) AS n_results", "rule, status").show()

    result = combined.project(
        "*, (CURRENT_TIMESTAMP AT TIME ZONE 'UTC') AS validated_at"
    )

    con.sql(
        """
        CREATE TABLE IF NOT EXISTS validation_results(
            participant_id VARCHAR,
            session_id VARCHAR,
            rule VARCHAR,
            status VARCHAR,
            observed BIGINT,
            expected BIGINT,
            validated_at TIMESTAMP NOT NULL
        )
        """
    )
    con.sql("BEGIN TRANSACTION")
    try:
        con.sql("DELETE FROM validation_results")
        insert_validation_results(con, result)
        con.sql("COMMIT")

    except Exception:
        con.sql("ROLLBACK")
        raise


if __name__ == "__main__":
    con = duckdb.connect("../../data/hbcd.duckdb")

    try:
        save_validation_results(con)
        con.sql("SELECT COUNT(*) FROM validation_results").show()

        # Repeat, and see if you get duplicates
        save_validation_results(con)
        con.sql("SELECT COUNT(*) FROM validation_results").show()

    finally:
        con.close()
