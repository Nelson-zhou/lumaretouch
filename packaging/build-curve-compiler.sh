#!/usr/bin/env bash
# Build the repository-owned Rust math helper; never download a runtime compiler.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/curve-compiler"}
command -v rustc >/dev/null || { echo 'rustc is required to build the curve compiler' >&2; exit 1; }
mkdir -p "$(dirname "$out")"
rustc --edition=2021 -O "$here/../core/curves/main.rs" -o "$out"
