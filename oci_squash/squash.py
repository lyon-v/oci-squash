import os
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pathlib

from .errors import SquashError
from .utils import normalize_abs


def _marker_files(tar: tarfile.TarFile, members: List[tarfile.TarInfo]):
    markers = {}
    for m in members:
        if ".wh." in m.name:
            markers[m] = tar.extractfile(m)
    return markers


def _file_should_be_skipped(name: str, to_skip: List[List[str]]) -> int:
    layer_nb = 1
    for layers in to_skip:
        for p in layers:
            if name == p or name.startswith(p + "/"):
                return layer_nb
        layer_nb += 1
    return 0


def _files_in_layers(
    root: Path, oci: bool, layer_ids: List[str]
) -> Dict[str, List[str]]:
    """Build a mapping of layer_id -> normalized file paths contained in that layer tar.

    Only non-empty (real) layers are considered.
    """
    files: Dict[str, List[str]] = {}
    for layer_id in layer_ids:
        if layer_id.startswith("<missing-"):
            continue
        layer_tar_path = _layer_tar_path(root, oci, layer_id)
        if not layer_tar_path.exists():
            continue
        with tarfile.open(layer_tar_path, "r", format=tarfile.PAX_FORMAT) as tar:
            files[layer_id] = [normalize_abs(n) for n in tar.getnames()]
    return files


def _path_hierarchy(path: str) -> List[str]:
    p = pathlib.PurePath(path)
    if len(p.parts) == 1:
        return list(p.parts)
    head = []
    acc: List[str] = []
    for part in p.parts[:-1]:
        head = [*head, part]
        acc.append(str(pathlib.PurePath(*head)))
    return acc


def _reduce_markers(markers: Dict[tarfile.TarInfo, tarfile.ExFileObject]) -> None:
    """Reduce marker files to a minimal necessary set in-place.

    Removes a marker if a higher-level marker (covering its parent directory)
    is also present.
    """
    if not markers:
        return
    marked_files = [normalize_abs(m.name.replace(".wh.", "")) for m in markers.keys()]
    to_remove: List[tarfile.TarInfo] = []
    for marker in list(markers.keys()):
        path = normalize_abs(marker.name.replace(".wh.", ""))
        for directory in _path_hierarchy(path):
            if directory in marked_files:
                to_remove.append(marker)
                break
    for marker in to_remove:
        markers.pop(marker, None)


def _add_markers(
    markers: Dict[tarfile.TarInfo, tarfile.ExFileObject],
    squashed_tar: tarfile.TarFile,
    files_in_layers: Dict[str, List[str]],
    added_symlinks: List[List[str]],
) -> None:
    """Add back necessary whiteout marker files to the squashed tar.

    Only add a marker if the referenced file exists in any of the preserved layers
    and it wasn't already added or on a symlink path to skip.
    """
    if not markers:
        return
    existing_files = [normalize_abs(n) for n in squashed_tar.getnames()]
    for marker, marker_file in markers.items():
        actual_file = marker.name.replace(".wh.", "")
        normalized_file = normalize_abs(actual_file)
        # Skip if on a symlink path
        if _file_should_be_skipped(normalized_file, added_symlinks):
            continue
        # Skip if it was already added for some reason
        if normalized_file in existing_files:
            continue
        # Decide if we need to add it based on files present in preserved layers
        should_add = False
        if files_in_layers:
            for files in files_in_layers.values():
                if normalized_file in files:
                    should_add = True
                    break
        else:
            should_add = True
        if should_add:
            # AUFS whiteouts are usually hardlinks; recreate as a regular file entry
            squashed_tar.addfile(tarfile.TarInfo(name=marker.name), marker_file)
            existing_files.append(normalize_abs(marker.name))


def squash_layers(
    layer_ids_to_squash: List[str],
    layer_ids_to_keep: List[str],
    old_root: Path,
    new_root: Path,
    oci: bool,
) -> Tuple[Optional[Path], List[str]]:
    squashed_dir = new_root / "squashed"
    squashed_dir.mkdir(parents=True, exist_ok=True)
    squashed_tar_path = squashed_dir / "layer.tar"

    # Find files in kept layers to help with whiteout processing later
    # For simplicity, we calculate on demand while iterating

    # Work through layers newest→oldest (reverse order), like original logic
    real_layers_to_squash = [
        lid for lid in layer_ids_to_squash if not lid.startswith("<missing-")
    ]
    real_layers_to_keep = [
        lid for lid in layer_ids_to_keep if not lid.startswith("<missing-")
    ]

    if not real_layers_to_squash:
        return None, real_layers_to_keep

    with tarfile.open(
        squashed_tar_path, "w", format=tarfile.PAX_FORMAT
    ) as squashed_tar:
        to_skip: List[List[str]] = []
        skipped_markers: Dict[tarfile.TarInfo, tarfile.ExFileObject] = {}
        skipped_sym_links: List[Dict[str, tarfile.TarInfo]] = []
        skipped_hard_links: List[Dict[str, tarfile.TarInfo]] = []
        skipped_files: List[Dict[str, tuple]] = []
        squashed_files: List[str] = []
        opaque_dirs: List[str] = []

        reading_layers: List[tarfile.TarFile] = []

        for layer_id in reversed(real_layers_to_squash):
            layer_tar_path = _layer_tar_path(old_root, oci, layer_id)
            if not layer_tar_path.exists():
                raise SquashError(f"Layer tar not found: {layer_tar_path}")
            layer_tar = tarfile.open(layer_tar_path, "r", format=tarfile.PAX_FORMAT)
            reading_layers.append(layer_tar)
            members = layer_tar.getmembers()
            markers = _marker_files(layer_tar, members)

            skipped_sym_link_files: Dict[str, tarfile.TarInfo] = {}
            skipped_hard_link_files: Dict[str, tarfile.TarInfo] = {}
            skipped_files_in_layer: Dict[str, tuple] = {}

            files_to_skip: List[str] = []
            layer_opaque_dirs: List[str] = []

            skipped_sym_links.append(skipped_sym_link_files)
            to_skip.append(files_to_skip)

            for marker, marker_file in markers.items():
                if marker.name.endswith(".wh..wh..opq"):
                    opaque_dir = os.path.dirname(marker.name)
                    layer_opaque_dirs.append(opaque_dir)
                else:
                    files_to_skip.append(normalize_abs(marker.name.replace(".wh.", "")))
                    skipped_markers[marker] = marker_file

            for member in members:
                normalized_name = normalize_abs(member.name)
                if _is_in_opaque_dir(member, opaque_dirs):
                    continue
                if member.issym():
                    skipped_sym_link_files[normalized_name] = member
                    continue
                if member in skipped_markers.keys():
                    continue
                if _file_should_be_skipped(normalized_name, skipped_sym_links):
                    f = (
                        member,
                        layer_tar.extractfile(member) if member.isfile() else None,
                    )
                    skipped_files_in_layer[normalized_name] = f
                    continue
                if _file_should_be_skipped(normalized_name, to_skip):
                    continue
                if normalized_name in squashed_files:
                    continue
                if member.islnk():
                    skipped_hard_link_files[normalized_name] = member
                    continue
                content = layer_tar.extractfile(member) if member.isfile() else None
                _add_file(member, content, squashed_tar, squashed_files, to_skip)

            skipped_hard_links.append(skipped_hard_link_files)
            skipped_files.append(skipped_files_in_layer)
            opaque_dirs += layer_opaque_dirs

        _add_hardlinks(squashed_tar, squashed_files, to_skip, skipped_hard_links)
        added_symlinks = _add_symlinks(
            squashed_tar, squashed_files, to_skip, skipped_sym_links
        )
        for layer in skipped_files:
            for member, content in layer.values():
                _add_file(member, content, squashed_tar, squashed_files, added_symlinks)

        # After assembling files, re-add necessary whiteout markers based on preserved layers
        if real_layers_to_keep:
            files_in_layers_to_keep = _files_in_layers(
                old_root, oci, real_layers_to_keep
            )
            _reduce_markers(skipped_markers)
            _add_markers(
                skipped_markers, squashed_tar, files_in_layers_to_keep, added_symlinks
            )

        for tar in reading_layers:
            tar.close()

    return squashed_tar_path, real_layers_to_keep


def _is_in_opaque_dir(member: tarfile.TarInfo, dirs: List[str]) -> bool:
    for d in dirs:
        if member.name == d or member.name.startswith(f"{d}/"):
            return True
    return False


def _layer_tar_path(root: Path, oci: bool, layer_id: str) -> Path:
    if oci:
        digest = layer_id.split(":", 1)[1] if ":" in layer_id else layer_id
        return root / "blobs" / "sha256" / digest
    else:
        digest = layer_id.split(":", 1)[1] if ":" in layer_id else layer_id
        return root / digest / "layer.tar"


def _add_hardlinks(squashed_tar, squashed_files, to_skip, skipped_hard_links):
    for layer, hardlinks_in_layer in enumerate(skipped_hard_links):
        current_layer = layer + 1
        for member in hardlinks_in_layer.values():
            normalized_name = normalize_abs(member.name)
            normalized_linkname = normalize_abs(member.linkname)
            layer_skip_name = _file_should_be_skipped(normalized_name, to_skip)
            layer_skip_linkname = _file_should_be_skipped(normalized_linkname, to_skip)
            if (
                layer_skip_name
                and current_layer > layer_skip_name
                or layer_skip_linkname
                and current_layer > layer_skip_linkname
                or normalized_name in squashed_files
                or normalized_linkname not in squashed_files
            ):
                pass
            else:
                squashed_files.append(normalized_name)
                squashed_tar.addfile(member)


def _add_file(member, content, squashed_tar, squashed_files, to_skip):
    normalized_name = normalize_abs(member.name)
    if normalized_name in squashed_files:
        return
    if _file_should_be_skipped(normalized_name, to_skip):
        return
    if content:
        squashed_tar.addfile(member, content)
    else:
        squashed_tar.addfile(member)
    squashed_files.append(normalized_name)


def _add_symlinks(squashed_tar, squashed_files, to_skip, skipped_sym_links):
    added_symlinks = []
    for layer, symlinks_in_layer in enumerate(skipped_sym_links):
        current_layer = layer + 1
        for member in symlinks_in_layer.values():
            normalized_name = normalize_abs(member.name)
            normalized_linkname = normalize_abs(member.linkname)
            if normalized_name in squashed_files:
                continue
            if _file_should_be_skipped(normalized_name, added_symlinks):
                continue
            layer_skip_name = _file_should_be_skipped(normalized_name, to_skip)
            layer_skip_linkname = _file_should_be_skipped(normalized_linkname, to_skip)
            if (layer_skip_name and current_layer > layer_skip_name) or (
                layer_skip_linkname and current_layer > layer_skip_linkname
            ):
                pass
            else:
                added_symlinks.append([normalized_name])
                squashed_files.append(normalized_name)
                squashed_tar.addfile(member)
    return added_symlinks
