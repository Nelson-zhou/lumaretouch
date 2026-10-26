#!/bin/sh
# AUTHORED / UNRUN. Explicit packaging only; never called at runtime.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$root/engine/src/lumaretouch_engine/bin"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$root/core/final_canvas_flip/final_canvas_flip.rs" -o "$root/engine/src/lumaretouch_engine/bin/liblrt_final_canvas_flip.so"
