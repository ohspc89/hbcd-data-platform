-- HBCD Data Platform SQL practice (synthetic; DuckDB)
-- One row per session, including incomplete sessions.
-- The four required motion TSVs are left/right x primary/calibration.
-- No duplicate recordings are simulated.

-- YOUR TICKET: Write a SELECT using CTEs, LEFT JOIN, conditional aggregation.
-- Return: participant_id, session_id, has_scans, has_left_primary,
-- has_right_primary, has_left_calibration, has_right_calibration,
-- ready_for_imu_qc (all 0/1). Exactly four rows.
-- For motion rows use suffix='motion', extension='.tsv', tracking_system='imu',
-- task='LeftLegMovement'/'RightLegMovement', acquisition='primary'/'calibration'.
-- has_scans means existence of scans.tsv, NOT validation PASS.
-- Preserve all sessions, even when they have no motion files.

-- TODO: YOUR QUERY HERE
WITH queried AS (
    SELECT
        participant_id,
        session_id,
        BOOL_OR(extension='.tsv' AND suffix='scans') AS has_scans,
        BOOL_OR(
            task='LeftLegMovement'
            AND tracking_system='imu'
            AND acquisition='primary'
            AND suffix='motion'
            AND extension='.tsv'
        ) AS has_left_primary,
        BOOL_OR(
            task='RightLegMovement'
            AND tracking_system='imu'
            AND acquisition='primary'
            AND suffix='motion'
            AND extension='.tsv'
        ) AS has_right_primary,
        BOOL_OR(
            task='LeftLegMovement'
            AND tracking_system='imu'
            AND acquisition='calibration'
            AND suffix='motion'
            AND extension='.tsv'
        ) AS has_left_calibration,
        BOOL_OR(
            task='RightLegMovement'
            AND tracking_system='imu'
            AND acquisition='calibration'
            AND suffix='motion'
            AND extension='.tsv'
        ) AS has_right_calibration,
    FROM file_manifest
    GROUP BY participant_id, session_id
), session_flags AS (
    SELECT
        s.participant_id,
        s.session_id,
        COALESCE(q.has_scans, FALSE) AS has_scans,
        COALESCE(q.has_left_primary, FALSE) AS has_left_primary,
        COALESCE(q.has_right_primary, FALSE) AS has_right_primary,
        COALESCE(q.has_left_calibration, FALSE) AS has_left_calibration,
        COALESCE(q.has_right_calibration, FALSE) AS has_right_calibration,
    FROM sessions s
    LEFT JOIN queried q
      ON s.participant_id = q.participant_id AND s.session_id = q.session_id
)
SELECT
    participant_id,
    session_id,
    has_scans,
    has_left_primary,
    has_right_primary,
    has_left_calibration,
    has_right_calibration,
    (
        has_scans
        AND has_left_primary
        AND has_right_primary
        AND has_left_calibration
        AND has_right_calibration
    ) AS ready_for_imu_qc
FROM session_flags
ORDER BY participant_id, session_id;
