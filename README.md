## OCI-Squash - Standalone Docker/OCI Image Layer Squashing Tool

A lightweight, dependency-free tool to squash Docker/OCI image layers from saved tar archives. It works fully offline (no Docker daemon required) and produces Docker-loadable tar output.

### Features

- **Zero Dependencies**: Pure Python standard library at runtime
- **Docker & OCI Support**: Auto-detects both formats; handles nested OCI indexes
- **Standalone**: Works on image tar files without Docker daemon
- **Docker-loadable Output**: Always emits Docker-style layers for reliable `docker load`
- **Metadata Preservation**: Maintains config/history and computes correct `diff_ids`
- **Whiteout Handling**: Properly reinjects marker files; supports opaque dirs
- **Tagging**: Set repository tag for the squashed image
- **Size Reporting**: Prints original vs squashed tar sizes and percentage change

### Installation

```bash
git clone https://github.com/your-username/oci-squash.git
cd oci-squash
# Optional: build a single-file binary
pip install -r requirements.txt
pyinstaller --onefile -n oci-squash -p . oci_squash/__main__.py
```

You can run it via Python:
```bash
python -m oci_squash.cli -h
```
or via the built binary:
```bash
./dist/oci-squash -h
```

### Usage

```text
usage: oci-squash [-h] [-f FROM_LAYER] [-t TAG] [-c [CLEANUP]] [-m MESSAGE] [--tmp-dir TMP_DIR] [-o OUTPUT_PATH] [-v] image

OCI/Docker image tar layer squashing tool

positional arguments:
  image                 Path to image tar file

options:
  -h, --help            show this help message and exit
  -f FROM_LAYER, --from-layer FROM_LAYER
                        Number of layers to squash or layer id
  -t TAG, --tag TAG     Tag for squashed image, e.g. repo/name:tag
  -c [CLEANUP], --cleanup [CLEANUP]
                        Cleanup the temporary directory (true/false). Default: true
  -m MESSAGE, --message MESSAGE
                        Commit message for the new image
  --tmp-dir TMP_DIR     Work directory to use (kept if provided)
  -o OUTPUT_PATH, --output-path OUTPUT_PATH
                        Output tar path for the squashed image
  -v, --verbose         Verbose output
```

Notes:
- `--from-layer` accepts either a number of layers from the top (e.g., `-f 3`) or an existing layer id/digest found in the image history/manifest.
- `--cleanup` is a boolean with default `true`. Use `--cleanup false` to keep the work directory for debugging.
- `--output-path` sets the output tar file. If omitted, a name is generated based on the new image id.

### Quick Start

1) Save an image to a tar archive:
```bash
docker save -o source.tar myrepo/myimage:latest
```

2) Squash the last N layers and write a new tar:
```bash
oci-squash -f 8 -t myrepo/myimage:squashed -m "squashed" -o squashed.tar source.tar
```

3) Load the resulting image into Docker:
```bash
docker load -i squashed.tar
```

4) Inspect the result:
```bash
docker history myrepo/myimage:squashed
```

### Example Output

Below is a real run showing tar size comparison and a successful load:
```text
2025-08-30 10:22:19,894 cli.py:106        INFO  Extracting tar: source.tar
2025-08-30 10:22:20,101 cli.py:109        INFO  Detected format: oci
2025-08-30 10:22:20,102 cli.py:116        INFO  Attempting to squash last 8 layers
2025-08-30 10:22:21,214 cli.py:162        INFO  Exporting to: squashed.tar
2025-08-30 10:22:21,646 cli.py:164        INFO  Done. New image id: sha256:0defd0fe8f1ea371...
2025-08-30 10:22:21,646 cli.py:171        INFO  Original tar size: 299.76 MB
2025-08-30 10:22:21,646 cli.py:172        INFO  Squashed tar size: 143.15 MB
2025-08-30 10:22:21,646 cli.py:175        INFO  Tar size decreased by 52.24 %
2025-08-30 10:22:21,737 cli.py:186        INFO  Squashed image Done.

Loaded image: myrepo/myimage:squashed
```

### How It Works (Brief)

- Extracts input tar into a work directory and detects format (Docker/OCI)
- Reads manifest and config; builds complete layer sequence (including virtual empty layers)
- Squashes selected layers by reassembling files, respecting whiteouts/opaque directories
- Always writes Docker-style output (`<digest>/layer.tar` and optional `squashed/layer.tar`)
- Recomputes `diff_ids` and config/rootfs/history; writes a new `manifest.json` and `repositories`
- Packs the new directory back into a tar that `docker load` can consume

### Tips

- Use `-v/--verbose` to print detailed processing steps
- Keep `--tmp-dir` to a local fast disk for better performance
- If you want to inspect the work directory, pass `--cleanup false`

### License

MIT
