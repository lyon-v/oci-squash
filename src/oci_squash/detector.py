from pathlib import Path
from typing import Literal

from .errors import SquashError


def detect_format(root: Path) -> Literal["docker", "oci"]:
    index = root / "index.json"
    manifest = root / "manifest.json"
    if index.exists():
        return "oci"
    if manifest.exists():
        return "docker"
    raise SquashError("Unable to detect image format - missing manifest files")
