import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .errors import SquashError


@dataclass
class ImageMeta:
    config: dict
    manifest: dict
    layer_ids: List[str]  # includes placeholders for empty layers
    real_layer_ids: List[str]  # excludes placeholders
    oci: bool


def _read_json(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def read_docker_metadata(root: Path) -> ImageMeta:
    manifest_path = root / "manifest.json"
    manifests = _read_json(manifest_path)
    if not manifests:
        raise SquashError("Empty manifest.json")
    manifest = manifests[0]

    config_path = root / manifest["Config"]
    config = _read_json(config_path)

    # Build layer ids from manifest layers (real only)
    real_layer_ids: List[str] = []
    for layer_path in manifest.get("Layers", []):
        layer_id = layer_path.split("/")[0]
        real_layer_ids.append(f"sha256:{layer_id}")

    # Build complete list from config.history including empty layers
    layer_ids: List[str] = []
    idx = 0
    for i, history in enumerate(config.get("history", [])):
        if history.get("empty_layer", False):
            layer_ids.append(f"<missing-{i}>")
        else:
            if idx < len(real_layer_ids):
                layer_ids.append(real_layer_ids[idx])
                idx += 1
            else:
                layer_ids.append(f"<missing-{i}>")

    return ImageMeta(
        config=config,
        manifest=manifest,
        layer_ids=layer_ids,
        real_layer_ids=real_layer_ids,
        oci=False,
    )


def read_oci_metadata(root: Path) -> ImageMeta:
    index = _read_json(root / "index.json")
    if not index.get("manifests"):
        raise SquashError("No manifests found in index.json")
    manifest_desc = index["manifests"][0]
    manifest_digest = manifest_desc["digest"].split(":", 1)[1]
    manifest_path = root / "blobs" / "sha256" / manifest_digest
    manifest = _read_json(manifest_path)

    # Nested index support
    if manifest.get("mediaType") == "application/vnd.oci.image.index.v1+json":
        if not manifest.get("manifests"):
            raise SquashError("No manifests in nested index")
        nested_desc = manifest["manifests"][0]
        nested_digest = nested_desc["digest"].split(":", 1)[1]
        manifest = _read_json(root / "blobs" / "sha256" / nested_digest)

    if "config" not in manifest:
        raise SquashError("No config found in manifest")
    config_digest = manifest["config"]["digest"].split(":", 1)[1]
    config = _read_json(root / "blobs" / "sha256" / config_digest)

    # Real layers from manifest
    real_layer_ids: List[str] = [l["digest"] for l in manifest.get("layers", [])]

    # Build combined list using history (with empty layers)
    layer_ids: List[str] = []
    idx = 0
    for i, history in enumerate(config.get("history", [])):
        if history.get("empty_layer", False):
            layer_ids.append(f"<missing-{i}>")
        else:
            if idx < len(real_layer_ids):
                layer_ids.append(real_layer_ids[idx])
                idx += 1
            else:
                layer_ids.append(f"<missing-{i}>")

    return ImageMeta(
        config=config,
        manifest=manifest,
        layer_ids=layer_ids,
        real_layer_ids=real_layer_ids,
        oci=True,
    )


def layer_tar_path(root: Path, oci: bool, layer_id: str) -> Optional[Path]:
    if layer_id.startswith("<missing-"):
        return None
    if oci:
        digest = layer_id.split(":", 1)[1] if ":" in layer_id else layer_id
        return root / "blobs" / "sha256" / digest
    else:
        digest = layer_id.split(":", 1)[1] if ":" in layer_id else layer_id
        return root / digest / "layer.tar"


def write_docker_manifest(
    root: Path,
    config_json_name: str,
    moved_layers: List[str],
    oci_input: bool,
    add_squashed_layer: bool,
    repo_tags: Optional[List[str]] = None,
) -> None:
    manifest = {
        "Config": config_json_name,
        "RepoTags": repo_tags or [],
        "Layers": [],
    }
    for lid in moved_layers:
        if lid.startswith("<missing-"):
            continue
        digest = lid.split(":", 1)[1] if ":" in lid else lid
        # Always write Docker-style layer paths in the output tar
        # so that `docker load` can consume it reliably.
        manifest["Layers"].append(f"{digest}/layer.tar")
    if add_squashed_layer:
        manifest["Layers"].append("squashed/layer.tar")
    with open(root / "manifest.json", "w") as f:
        json.dump([manifest], f, indent=2)


def write_repositories(root: Path, image_id: str, repo_tags: List[str]) -> None:
    repositories = {}
    short_id = image_id.split(":", 1)[1] if ":" in image_id else image_id
    for tag in repo_tags:
        if ":" in tag:
            repo, t = tag.rsplit(":", 1)
        else:
            repo, t = tag, "latest"
        repositories.setdefault(repo, {})[t] = short_id
    if repositories:
        with open(root / "repositories", "w") as f:
            json.dump(repositories, f, indent=2)


def copy_preserved_layers(
    old_root: Path, new_root: Path, oci_input: bool, layer_ids_to_keep: List[str]
) -> None:
    new_root.mkdir(parents=True, exist_ok=True)
    for layer_id in layer_ids_to_keep:
        if layer_id.startswith("<missing-"):
            continue
        if oci_input:
            # Convert OCI blob (possibly compressed) into Docker-style <digest>/layer.tar (uncompressed)
            import tarfile

            digest = layer_id.split(":", 1)[1] if ":" in layer_id else layer_id
            src_blob = old_root / "blobs" / "sha256" / digest
            if not src_blob.exists():
                continue
            dest_dir = new_root / digest
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_tar = dest_dir / "layer.tar"
            # Read input tar (auto-detect compression) and re-pack uncompressed
            with tarfile.open(src_blob, mode="r:*") as in_tar:
                with tarfile.open(
                    dest_tar, mode="w", format=tarfile.PAX_FORMAT
                ) as out_tar:
                    for member in in_tar.getmembers():
                        # Extract fileobj if regular file, otherwise add member as-is
                        if member.isfile():
                            fobj = in_tar.extractfile(member)
                            out_tar.addfile(member, fobj)
                        else:
                            out_tar.addfile(member)
        else:
            digest = layer_id.split(":", 1)[1] if ":" in layer_id else layer_id
            src_dir = old_root / digest
            src_tar = src_dir / "layer.tar"
            if not src_tar.exists():
                continue
            dest_dir = new_root / digest
            dest_dir.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(src_tar, dest_dir / "layer.tar")
            # copy json if exists
            src_json = src_dir / "json"
            if src_json.exists():
                shutil.copy2(src_json, dest_dir / "json")
            src_ver = src_dir / "VERSION"
            if src_ver.exists():
                shutil.copy2(src_ver, dest_dir / "VERSION")
