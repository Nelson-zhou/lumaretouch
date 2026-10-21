#!/usr/bin/env bash
# Build the bounded Rust colour-analysis worker from this checkout only.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/color-scopes"}
command -v rustc >/dev/null || { echo 'rustc is required to build color-scopes' >&2; exit 1; }
mkdir -p "$(dirname "$out")"
rustc --edition=2021 -O "$here/../core/color_scopes/main.rs" -o "$out"
