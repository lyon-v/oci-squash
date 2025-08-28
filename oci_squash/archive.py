import os
import tarfile
from pathlib import Path
from typing import Optional

from .errors import SquashError


def extract(tar_path: Path, dest_dir: Path) -> None:
    if not tar_path.exists():
        raise SquashError(f"Tar file not found: {tar_path}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(tar_path, "r") as tar:
            tar.extractall(dest_dir)
    except Exception as e:
        raise SquashError(f"Failed to extract tar file: {e}")


def pack(src_dir: Path, out_tar: Path) -> None:
    out_tar.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out_tar, "w", format=tarfile.PAX_FORMAT) as tar:
        for root, _, files in os.walk(src_dir):
            for name in files:
                path = Path(root) / name
                arcname = path.relative_to(src_dir)
                tar.add(path, arcname=str(arcname))
