-- HBCD Data Platform SQL practice (synthetic; DuckDB)
-- One row per session, including incomplete sessions.
-- The four required motion TSVs are left/right x primary/calibration.
-- No duplicate recordings are simulated.
CREATE TABLE file_manifest (
 participant_id VARCHAR, session_id VARCHAR, relative_path VARCHAR,
 extension VARCHAR, suffix VARCHAR, task VARCHAR,
 tracking_system VARCHAR, acquisition VARCHAR
);

-- A session is anchored by its sub-*_sessions.tsv listing in real BIDS;
-- this synthetic session inventory explicitly includes sessions with missing motion files.
CREATE TABLE sessions (participant_id VARCHAR, session_id VARCHAR);
INSERT INTO sessions VALUES
 ('2000000001','V02'),('2000000001','V03'),
 ('2000000002','V02'),('2000000002','V03');

INSERT INTO file_manifest VALUES
-- Complete session
('2000000001','V02','sub-2000000001/ses-V02/sub-2000000001_ses-V02_scans.tsv','.tsv','scans',NULL,NULL,NULL),
('2000000001','V02','sub-2000000001/ses-V02/motion/sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv','.tsv','motion','LeftLegMovement','imu','primary'),
('2000000001','V02','sub-2000000001/ses-V02/motion/sub-2000000001_ses-V02_task-RightLegMovement_tracksys-imu_acq-primary_motion.tsv','.tsv','motion','RightLegMovement','imu','primary'),
('2000000001','V02','sub-2000000001/ses-V02/motion/sub-2000000001_ses-V02_task-LeftLegMovement_tracksys-imu_acq-calibration_motion.tsv','.tsv','motion','LeftLegMovement','imu','calibration'),
('2000000001','V02','sub-2000000001/ses-V02/motion/sub-2000000001_ses-V02_task-RightLegMovement_tracksys-imu_acq-calibration_motion.tsv','.tsv','motion','RightLegMovement','imu','calibration'),
-- Missing left calibration
('2000000001','V03','sub-2000000001/ses-V03/sub-2000000001_ses-V03_scans.tsv','.tsv','scans',NULL,NULL,NULL),
('2000000001','V03','sub-2000000001/ses-V03/motion/sub-2000000001_ses-V03_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv','.tsv','motion','LeftLegMovement','imu','primary'),
('2000000001','V03','sub-2000000001/ses-V03/motion/sub-2000000001_ses-V03_task-RightLegMovement_tracksys-imu_acq-primary_motion.tsv','.tsv','motion','RightLegMovement','imu','primary'),
('2000000001','V03','sub-2000000001/ses-V03/motion/sub-2000000001_ses-V03_task-RightLegMovement_tracksys-imu_acq-calibration_motion.tsv','.tsv','motion','RightLegMovement','imu','calibration'),
-- Four motion files, missing scans.tsv (synthetic defensive edge case)
('2000000002','V02','sub-2000000002/ses-V02/motion/sub-2000000002_ses-V02_task-LeftLegMovement_tracksys-imu_acq-primary_motion.tsv','.tsv','motion','LeftLegMovement','imu','primary'),
('2000000002','V02','sub-2000000002/ses-V02/motion/sub-2000000002_ses-V02_task-RightLegMovement_tracksys-imu_acq-primary_motion.tsv','.tsv','motion','RightLegMovement','imu','primary'),
('2000000002','V02','sub-2000000002/ses-V02/motion/sub-2000000002_ses-V02_task-LeftLegMovement_tracksys-imu_acq-calibration_motion.tsv','.tsv','motion','LeftLegMovement','imu','calibration'),
('2000000002','V02','sub-2000000002/ses-V02/motion/sub-2000000002_ses-V02_task-RightLegMovement_tracksys-imu_acq-calibration_motion.tsv','.tsv','motion','RightLegMovement','imu','calibration'),
-- Empty motion session, scans.tsv present
('2000000002','V03','sub-2000000002/ses-V03/sub-2000000002_ses-V03_scans.tsv','.tsv','scans',NULL,NULL,NULL);

-- YOUR TICKET: Write a SELECT using CTEs, LEFT JOIN, conditional aggregation.
-- Return: participant_id, session_id, has_scans, has_left_primary,
-- has_right_primary, has_left_calibration, has_right_calibration,
-- ready_for_imu_qc (all 0/1). Exactly four rows.
-- For motion rows use suffix='motion', extension='.tsv', tracking_system='imu',
-- task='LeftLegMovement'/'RightLegMovement', acquisition='primary'/'calibration'.
-- has_scans means existence of scans.tsv, NOT validation PASS.
-- Preserve all sessions, even when they have no motion files.

-- TODO: YOUR QUERY HERE
