import os
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
