from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("path", help="path to hbcd raw data")


def parse_raw_bids_filename(filename):
    """
    Parse a Raw BIDS filename

    Parameters
    ----------
    filename: str
        Name of a file

    Returns
    -------
    entities: dict
    """
    entities = {}
    no_ext = Path(filename).stem
    if "-" in no_ext:
        parts = no_ext.split("_")

        for part in parts:
            if "-" in part:
                key, value = part.split("-", 1)
                entities[key] = value
            else:
                entities["suffix"] = part
    else:
        entities["suffix"] = no_ext

    return entities


def scan_files(root_path):
    """
    Scan all files under root_path

    Parameters
    ----------
    root_path: str
        Path to the root directory of raw BIDS data

    Returns
    -------
    records: list[dict]
    """
    root_path = Path(root_path)
    records = []
    for path in root_path.rglob("*"):
        if not path.is_file():
            continue

        if path.name.startswith("."):
            continue

        stat = path.stat()

        record = {
            "filename": path.name,
            "relative_path": str(path.relative_to(root_path)),
            "extension": path.suffix,
            "size_bytes": stat.st_size,
            "modified_time": stat.st_mtime,
        }
        record.update(parse_raw_bids_filename(path.name))

        records.append(record)

    return records

    
if __name__ == "__main__":
    args = parser.parse_args()

    records = scan_files(args.path)

    print(f"Found {len(records):,} files")
    print(records[:20])
