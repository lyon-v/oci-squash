import hashlib
import json
from pathlib import Path
from typing import List, Optional

from .utils import utc_now_rfc3339_trimmed


def compute_diff_ids(
    moved_layer_paths: List[Path], squashed_layer_path: Optional[Path]
) -> List[str]:
    diff_ids: List[str] = []
    for p in moved_layer_paths:
        diff_ids.append(_sha256_of_file(p))
    if squashed_layer_path is not None and squashed_layer_path.exists():
        diff_ids.append(_sha256_of_file(squashed_layer_path))
    return diff_ids


def _sha256_of_file(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(10485760)
            if not data:
                break
            sha.update(data)
    return sha.hexdigest()


def compute_chain_ids(diff_ids: List[str]) -> List[str]:
    chain_ids: List[str] = []
    _generate_chain_id(chain_ids, diff_ids, None)
    return chain_ids


def _generate_chain_id(
    chain_ids: List[str], diff_ids: List[str], parent_chain_id: Optional[str]
):
    if parent_chain_id is None:
        if not diff_ids:
            return None
        return _generate_chain_id(chain_ids, diff_ids[1:], diff_ids[0])
    chain_ids.append(parent_chain_id)
    if not diff_ids:
        return parent_chain_id
    to_hash = f"sha256:{parent_chain_id} sha256:{diff_ids[0]}"
    digest = hashlib.sha256(to_hash.encode("utf8")).hexdigest()
    return _generate_chain_id(chain_ids, diff_ids[1:], digest)


def update_config_and_history(
    old_config: dict,
    kept_layers: List[str],
    new_diff_ids: List[str],
    comment: str,
) -> dict:
    metadata = json.loads(json.dumps(old_config))
    created = utc_now_rfc3339_trimmed()
    metadata["created"] = created
    # Trim history to kept layers length (history includes empty layers)
    metadata["history"] = metadata.get("history", [])[: len(kept_layers)]
    # Rebuild rootfs.diff_ids from provided new_diff_ids
    if "rootfs" not in metadata:
        metadata["rootfs"] = {"type": "layers", "diff_ids": []}
    # Ensure entries are prefixed with sha256:
    metadata["rootfs"]["diff_ids"] = [
        f"sha256:{d}" if not str(d).startswith("sha256:") else str(d)
        for d in new_diff_ids
    ]
    # Append history entry for squashed operation
    history = {"comment": comment or "Squashed layers", "created": created}
    if not new_diff_ids:
        # No real squashed tar created; mark as empty layer to keep history consistent
        history["empty_layer"] = True
    metadata.setdefault("history", []).append(history)
    return metadata


def write_config_and_get_image_id(new_root: Path, config: dict) -> tuple[str, str]:
    json_metadata = json.dumps(config, sort_keys=True, separators=(",", ":")) + "\n"
    image_id_hex = hashlib.sha256(json_metadata.encode()).hexdigest()
    file_name = f"{image_id_hex}.json"
    with open(new_root / file_name, "w") as f:
        f.write(json_metadata)
    return f"sha256:{image_id_hex}", file_name
