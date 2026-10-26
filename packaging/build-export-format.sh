#!/usr/bin/env bash
# Authored build recipe only; UNRUN during source authoring, never run at runtime.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:-$here/../engine/src/lumaretouch_engine/bin/liblrt_export_format.so}"
mkdir -p "$(dirname "$out")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$here/../core/export_format/lib.rs" -o "$out"
