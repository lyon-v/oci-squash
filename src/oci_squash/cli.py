import argparse
import logging
import shutil
import tempfile
from pathlib import Path

from . import archive
from .detector import detect_format
from .errors import SquashError, SquashUnnecessaryError
from .formats import (
    copy_preserved_layers,
    layer_tar_path as fmt_layer_tar_path,
    read_docker_metadata,
    read_oci_metadata,
    write_docker_manifest,
    write_repositories,
)
from .metadata import (
    compute_diff_ids,
    update_config_and_history,
    write_config_and_get_image_id,
)
from .squash import squash_layers
from .utils import setup_logger


def _str2bool(v: str) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "t", "yes", "y"):  # truthy
        return True
    if s in ("0", "false", "f", "no", "n"):  # falsy
        return False
    raise argparse.ArgumentTypeError("Boolean value expected (true/false)")


def parse_args():
    p = argparse.ArgumentParser(description="OCI/Docker image tar layer squashing tool")
    p.add_argument("image", help="Path to image tar file")
    p.add_argument("-f", "--from-layer", help="Number of layers to squash or layer id")
    p.add_argument("-t", "--tag", help="Tag for squashed image, e.g. repo/name:tag")
    p.add_argument(
        "-c",
        "--cleanup",
        type=_str2bool,
        nargs="?",
        const=True,
        default=True,
        help="Cleanup the temporary directory (true/false). Default: true",
    )
    p.add_argument(
        "-m", "--message", default="", help="Commit message for the new image"
    )
    p.add_argument("--tmp-dir", help="Work directory to use (kept if provided)")
    p.add_argument("-o", "--output-path", help="Output tar path for the squashed image")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    return p.parse_args()


def compute_layers_to_squash(all_layers, from_layer):
    total = len(all_layers)
    if from_layer is None:
        number = total
    else:
        try:
            number = int(from_layer)
        except (TypeError, ValueError):
            if from_layer in all_layers:
                number = total - all_layers.index(from_layer) - 1
            else:
                raise SquashError(f"Layer not found: {from_layer}")
    if number <= 0 or number > total:
        raise SquashError(f"Invalid number of layers to squash: {number}")
    marker = total - number
    to_keep = all_layers[:marker]
    to_squash = all_layers[marker:]
    if len(to_squash) < 1:
        raise SquashError("Invalid number of layers to squash: 0")
    if len(to_squash) == 1:
        raise SquashUnnecessaryError(
            "Single layer marked to squash, no squashing is required"
        )
    return to_keep, to_squash


def run():
    args = parse_args()
    log = setup_logger(args.verbose)
    image_tar = Path(args.image)
    if not image_tar.exists():
        raise SquashError(f"Input tar not found: {image_tar}")

    work_root = Path(args.tmp_dir) if args.tmp_dir else None

    if work_root is None:
        work_root = Path(tempfile.mkdtemp(prefix="oci-squash-"))

    log.debug(f"Work root: {work_root}")
    old_dir = work_root / "old"
    new_dir = work_root / "new"
    old_dir.mkdir(parents=True, exist_ok=True)
    new_dir.mkdir(parents=True, exist_ok=True)

    try:
        log.info(f"Extracting tar: {image_tar}")
        archive.extract(image_tar, old_dir)
        fmt = detect_format(old_dir)
        log.info(f"Detected format: {fmt}")
        if fmt == "oci":
            meta = read_oci_metadata(old_dir)
        else:
            meta = read_docker_metadata(old_dir)

        to_keep, to_squash = compute_layers_to_squash(meta.layer_ids, args.from_layer)
        log.info(f"Attempting to squash last {len(to_squash)} layers")

        squashed_tar, kept_real = squash_layers(
            to_squash, to_keep, old_dir, new_dir, meta.oci
        )

        # Copy preserved layers into new image directory
        copy_preserved_layers(old_dir, new_dir, meta.oci, to_keep)

        # Build list of moved layer tar paths in new_root (real only)
        moved_paths = []
        for lid in to_keep:
            if lid.startswith("<missing-"):
                continue
            # We always write Docker-style layers (<digest>/layer.tar) in the output
            p = fmt_layer_tar_path(new_dir, False, lid)
            if p and p.exists():
                moved_paths.append(p)

        diff_ids = compute_diff_ids(moved_paths, squashed_tar)

        # Update config and history
        new_config = update_config_and_history(
            meta.config, to_keep, diff_ids, args.message
        )
        image_id, config_name = write_config_and_get_image_id(new_dir, new_config)

        # Manifest + repositories
        repo_tags = [args.tag] if args.tag else None
        write_docker_manifest(
            new_dir,
            config_name,
            to_keep,
            meta.oci,
            add_squashed_layer=bool(squashed_tar),
            repo_tags=repo_tags,
        )
        if repo_tags:
            write_repositories(new_dir, image_id, repo_tags)

        # Export
        output_path = (
            Path(args.output_path)
            if args.output_path
            else image_tar.parent / f"squashed-{image_id.split(':', 1)[1][:12]}.tar"
        )
        log.info(f"Exporting to: {output_path}")
        archive.pack(new_dir, output_path)
        log.info(f"Done. New image id: {image_id}")
        # Size comparison (compressed tar sizes)
        try:
            in_sz = image_tar.stat().st_size
            out_sz = Path(output_path).stat().st_size
            in_mb = in_sz / 1024 / 1024
            out_mb = out_sz / 1024 / 1024
            log.info("Original tar size: %.2f MB" % in_mb)
            log.info("Squashed tar size: %.2f MB" % out_mb)
            if out_sz <= in_sz and in_sz > 0:
                saved_pct = ((in_mb - out_mb) / in_mb) * 100.0
                log.info("Tar size decreased by %.2f %%" % saved_pct)
            elif out_sz > in_sz and in_sz > 0:
                inc_pct = ((out_mb - in_mb) / in_mb) * 100.0
                log.info("Tar size increased by %.2f %%" % inc_pct)
        except Exception:
            # Best-effort; do not fail the run if size check fails
            pass
    finally:
        if args.cleanup:
            shutil.rmtree(work_root, ignore_errors=True)
            log.debug(f"Removed work root: {work_root}")
        log.info("Squashed image Done.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logging.getLogger("oci_squash").error(str(e))
        raise
