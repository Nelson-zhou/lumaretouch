#!/usr/bin/env bash
# Builds only this checkout's bounded studio background mask worker.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/studio-background"}
command -v rustc >/dev/null || { echo 'rustc is required to build studio-background' >&2; exit 1; }
mkdir -p "$(dirname "$out")"
rustc --edition=2021 -O "$here/../core/studio_background/main.rs" -o "$out"
