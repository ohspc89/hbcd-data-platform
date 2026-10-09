from pathlib import Path
import logging
import duckdb

from hbcd_data_platform.load_manifest import load_manifest
from hbcd_data_platform.validate_manifest import save_validation_results


logger = logging.getLogger(__name__)


def run_pipeline(raw_path, db_path):
    logger.info("Pipeline started")
    load_manifest(raw_path, db_path)

    logger.info("Ingestion completed")

    if not Path(db_path).is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    con = duckdb.connect(db_path)
    try:
        save_validation_results(con)
        logger.info("Validation completed")
    except Exception:
        logger.exception("Validation failed")
        raise
    finally:
        con.close()
    
    logger.info("Pipeline finished")
