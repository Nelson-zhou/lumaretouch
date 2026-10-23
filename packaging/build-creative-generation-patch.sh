#!/usr/bin/env bash
# Authored build recipe only; not run during source authoring or at runtime.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:-$here/../engine/src/lumaretouch_engine/bin/liblrt_creative_generation_patch.so}"
mkdir -p "$(dirname "$out")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$here/../core/creative_generation_patch/lib.rs" -o "$out"
