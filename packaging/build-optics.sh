#!/usr/bin/env bash
# Explicit local build only. This script downloads/installs nothing.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_optics.so"}
command -v rustc >/dev/null || { echo 'rustc is required for the optics kernel' >&2; exit 1; }
mkdir -p "$(dirname "$out")"
rustc --edition=2021 --crate-type cdylib -C panic=abort -O "$here/../core/optics/lib.rs" -o "$out"
