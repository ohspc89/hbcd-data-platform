import logging

import duckdb

from hbcd_data_platform.config import PipelineConfig, validate_pipeline_config
from hbcd_data_platform.load_manifest import load_manifest
from hbcd_data_platform.validate_manifest import save_validation_results

logger = logging.getLogger(__name__)


def run_pipeline(config: PipelineConfig) -> None:
    logger.info("Pipeline started")

    validate_pipeline_config(config)

    load_manifest(config.raw_path, config.db_path)

    logger.info("Ingestion completed")

    if not config.db_path.is_file():
        raise FileNotFoundError(f"Database not found: {config.db_path}")

    con = duckdb.connect(config.db_path)
    try:
        save_validation_results(con)
        logger.info("Validation completed")
    except Exception:
        logger.exception("Validation failed")
        raise
    finally:
        con.close()

    logger.info("Pipeline finished")
