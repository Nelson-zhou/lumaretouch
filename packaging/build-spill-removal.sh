#!/usr/bin/env bash
# Authored build recipe only. Never called automatically at product runtime.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:-$here/../engine/src/lumaretouch_engine/bin/liblrt_spill_removal.so}"
mkdir -p "$(dirname "$out")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$here/../core/spill_removal/lib.rs" -o "$out"
