#!/usr/bin/env bash
# Build this checkout's original dependency-free reviewed-background core.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_id_background.so"}
command -v rustc >/dev/null || { echo 'rustc is required for reviewed ID background' >&2; exit 1; }
mkdir -p "$(dirname "$out")"
rustc --edition=2021 --crate-type cdylib -O "$here/../core/id_background/lib.rs" -o "$out"
