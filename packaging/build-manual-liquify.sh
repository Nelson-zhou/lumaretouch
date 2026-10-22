#!/usr/bin/env bash
# Compile the bounded retained-vector field worker from this checkout only.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/manual-liquify"}
command -v rustc >/dev/null || { echo 'rustc is required to build manual-liquify' >&2; exit 1; }
mkdir -p "$(dirname "$out")"
rustc --edition=2021 -O "$here/../core/manual_liquify/main.rs" -o "$out"
