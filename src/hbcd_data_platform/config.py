from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    """Store filesystem paths used by the pipeline."""
    raw_path: Path
    db_path: Path


def validate_pipeline_config(config: PipelineConfig) -> None:
    if not config.raw_path.exists():
        raise FileNotFoundError(f"Directory does not exist: '{config.raw_path}'")
    if not config.raw_path.is_dir():
        raise NotADirectoryError(f"Not a directory: '{config.raw_path}'")
