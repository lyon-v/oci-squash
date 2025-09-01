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
pip install oci-squash
docker save -o source.tar myrepo/myimage:latest
oci-squash -f 3 -t myrepo/myimage:squashed -o squashed.tar source.tar
docker load -i squashed.tar
```

### End-to-end Example

This example squashes the last 8 layers of `lyonv/ubuntu-dev:latest`, saves to `squashed.tar`, loads it back, and shows the reduced history and tar size.

1) Inspect original image history:
```bash
docker history lyonv/ubuntu-dev:latest
```

```text
IMAGE          CREATED         CREATED BY                                      SIZE      COMMENT
b23aed85a512   10 hours ago    RUN /bin/sh -c rm -f /bigfile # buildkit        0B        buildkit.dockerfile.v0
<missing>      10 hours ago    RUN /bin/sh -c dd if=/dev/zero of=/bigfile b…   105MB     buildkit.dockerfile.v0
<missing>      10 hours ago    WORKDIR /app && USER appuser &&     echo Ver…   0B        buildkit.dockerfile.v0
<missing>      10 hours ago    RUN /bin/sh -c apt-get clean &&     rm -rf /…   4.1kB     buildkit.dockerfile.v0
<missing>      10 hours ago    RUN /bin/sh -c mkdir -p /app/{conf,logs} /va…   0B        buildkit.dockerfile.v0
<missing>      10 hours ago    RUN /bin/sh -c apt-get install -y --no-insta…   2.83MB    buildkit.dockerfile.v0
<missing>      10 hours ago    RUN /bin/sh -c apt-get install -y --no-insta…   78.1MB    buildkit.dockerfile.v0
<missing>      10 hours ago    RUN /bin/sh -c ln -snf /usr/share/zoneinfo/A…   58.4MB    buildkit.dockerfile.v0
<missing>      11 months ago   sh -c sleep 36000                               4.1kB     build img
<missing>      15 months ago   /bin/sh -c #(nop)  CMD ["/bin/bash"]            0B        
<missing>      15 months ago   /bin/sh -c #(nop) ADD file:e7cff353f027ecf0a…   79.5MB    
<missing>      15 months ago   /bin/sh -c #(nop)  LABEL org.opencontainers.…   0B        
<missing>      15 months ago   /bin/sh -c #(nop)  LABEL org.opencontainers.…   0B        
<missing>      15 months ago   /bin/sh -c #(nop)  ARG LAUNCHPAD_BUILD_ARCH     0B        
<missing>      15 months ago   /bin/sh -c #(nop)  ARG RELEASE                  0B        
```

2) Save, squash, and load:
```bash
docker save -o source.tar  lyonv/ubuntu-dev:latest
oci-squash -f 8 -t lyonv/ubuntu-dev:squashed -m squashed -o squashed.tar source.tar
docker load -i squashed.tar
```

Sample run output:
```text
2025-08-30 17:18:56,654 cli.py:106        INFO  Extracting tar: source.tar
2025-08-30 17:18:56,859 cli.py:109        INFO  Detected format: oci
2025-08-30 17:18:56,859 cli.py:116        INFO  Attempting to squash last 8 layers
2025-08-30 17:18:57,965 cli.py:162        INFO  Exporting to: squashed.tar
2025-08-30 17:18:58,393 cli.py:164        INFO  Done. New image id: sha256:1ae6a77f5b834850e9a9b2c4e3a6f8f715efb8c46af92635a49640c53e3db347
2025-08-30 17:18:58,393 cli.py:171        INFO  Original tar size: 299.76 MB
2025-08-30 17:18:58,393 cli.py:172        INFO  Squashed tar size: 143.15 MB
2025-08-30 17:18:58,393 cli.py:175        INFO  Tar size decreased by 52.24 %
2025-08-30 17:18:58,484 cli.py:186        INFO  Squashed image Done.

Loaded image: lyonv/ubuntu-dev:squashed
```

3) Inspect the squashed image history:
```bash
docker history lyonv/ubuntu-dev:squashed
```

```text
IMAGE          CREATED          CREATED BY                                      SIZE      COMMENT
927444bd87b4   31 seconds ago                                                   79.9MB    squashed
<missing>      11 months ago    sh -c sleep 36000                               4.1kB     build img
<missing>      15 months ago    /bin/sh -c #(nop)  CMD ["/bin/bash"]            0B        
<missing>      15 months ago    /bin/sh -c #(nop) ADD file:e7cff353f027ecf0a…   79.5MB    
<missing>      15 months ago    /bin/sh -c #(nop)  LABEL org.opencontainers.…   0B        
<missing>      15 months ago    /bin/sh -c #(nop)  LABEL org.opencontainers.…   0B        
<missing>      15 months ago    /bin/sh -c #(nop)  ARG LAUNCHPAD_BUILD_ARCH     0B        
<missing>      15 months ago    /bin/sh -c #(nop)  ARG RELEASE                  0B        
```

In this run, the tar reduced from 299.76 MB to 143.15 MB, a 52.24% decrease.

You can run it via Python (local dev tree):
```bash
PYTHONPATH=src python -m oci_squash.cli -h
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
