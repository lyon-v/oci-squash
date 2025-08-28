# OCI-Squash - Standalone Docker/OCI Image Layer Squashing Tool

A lightweight, dependency-free Python tool for squashing Docker and OCI image layers from tar files without requiring Docker daemon. This tool can significantly reduce image size by merging multiple layers into a single layer while preserving image functionality.

## 🚀 Features

- **🔧 Zero Dependencies**: Uses only Python standard library
- **🐳 Docker & OCI Support**: Automatically detects and handles both Docker and OCI image formats
- **📦 Nested OCI Index Support**: Handles complex OCI structures (e.g., multi-architecture images)
- **⚡ Standalone Operation**: No Docker daemon required
- **🛡️ Metadata Preservation**: Maintains image configuration, history, and compatibility
- **🏷️ Tag Support**: Set custom tags for squashed images
- **📊 Size Reporting**: Shows before/after size comparison
- **🔄 Layer Analysis**: Intelligent handling of empty layers, symlinks, and hardlinks
- **⚠️ Marker File Support**: Properly handles Docker whiteout files

## 📖 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Command Line Options](#command-line-options)
- [Examples](#examples)
- [How It Works](#how-it-works)
- [Supported Formats](#supported-formats)
- [Limitations](#limitations)
- [Development](#development)
- [License](#license)

## 📦 Installation

### From Source
```bash
git clone https://github.com/your-username/oci-squash.git
cd oci-squash
```

### Requirements
- Python 3.6+
- No external dependencies required
 
