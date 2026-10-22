#!/usr/bin/env bash
# Build the source-domain local mask worker from this checkout only.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/local-masks"}
command -v rustc >/dev/null || { echo 'rustc is required to build local-masks' >&2; exit 1; }
mkdir -p "$(dirname "$out")"
rustc --edition=2021 -O "$here/../core/local_masks/main.rs" -o "$out"
