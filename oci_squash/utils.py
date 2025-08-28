import contextlib
import datetime
import hashlib
import logging
import os
import pathlib
import re
import tempfile
from typing import Iterator, Optional, Union


def utc_now_rfc3339_trimmed() -> str:
    date = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return re.sub(r"0*Z$", "Z", date)


class Chdir(object):
    def __init__(self, new_path: Union[str, os.PathLike[str]]):
        self.newPath = os.path.expanduser(str(new_path))

    def __enter__(self):
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.savedPath)


def normalize_abs(path: Union[str, pathlib.Path]) -> str:
    return os.path.normpath(os.path.join("/", str(path)))


@contextlib.contextmanager
def tempdir(prefix: str = "oci-squash-") -> Iterator[str]:
    d = tempfile.mkdtemp(prefix=prefix)
    try:
        yield d
    finally:
        import shutil

        shutil.rmtree(d, ignore_errors=True)


def ensure_dir(path: Union[str, os.PathLike[str]]):
    os.makedirs(path, exist_ok=True)


def sha256_of_file(path: Union[str, os.PathLike[str]]) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(10485760)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def setup_logger(verbose: bool = False) -> logging.Logger:
    handler_out = logging.StreamHandler()
    log = logging.getLogger("oci_squash")
    if not log.handlers:
        fmt = logging.Formatter(
            "%(asctime)s %(filename)s:%(lineno)-10s %(levelname)-5s %(message)s"
        )
        handler_out.setFormatter(fmt)
        log.addHandler(handler_out)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    return log
