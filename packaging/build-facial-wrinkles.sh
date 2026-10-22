#!/usr/bin/env bash
# Explicit packaging build only. Downloads/installs nothing; no runtime build.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_facial_wrinkles.so"}
command -v rustc >/dev/null || { echo 'rustc is required for the facial wrinkle compositor' >&2; exit 1; }
mkdir -p "$(dirname "$out")"
rustc --edition=2021 --crate-type cdylib -C panic=abort -O "$here/../core/facial_wrinkles/lib.rs" -o "$out"
