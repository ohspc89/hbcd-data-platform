import re
from pathlib import Path

import numpy as np
import pandas as pd


def make_synthetic_imu_tsv(path: Path) -> None:
    task_pattern = re.compile(r"task-(Left|Right)LegMovement")

    candidate_task = task_pattern.search(path.stem)

    if candidate_task is not None:
        task = candidate_task.group(1)
    else:
        raise ValueError(f"filename not correct: '{path}'")

    columns = [
        "imu_latency",
        f"{task}Ankle_ACCEL_x",
        f"{task}Ankle_ACCEL_y",
        f"{task}Ankle_ACCEL_z",
        f"{task}Ankle_GYRO_x",
        f"{task}Ankle_GYRO_y",
        f"{task}Ankle_GYRO_z",
    ]
    df = pd.DataFrame(
            np.vstack(
                (
                    np.arange(200) / 25,
                    np.zeros(200),
                    np.ones(200),
                    np.zeros(200),
                    np.full(200, 100),
                    np.full(200, 100),
                    np.full(200, 100),
                )
            ).T
         )
    df.columns = columns
    df.to_csv(path, sep="\t", index=False)
