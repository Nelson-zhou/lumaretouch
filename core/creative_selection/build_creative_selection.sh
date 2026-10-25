#!/bin/sh
# AUTHORED / UNRUN. Run only after execution is separately authorized.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
OUT=${1:-"$ROOT/engine/src/lumaretouch_engine/bin/liblumaretouch_creative_selection.so"}
mkdir -p "$(dirname -- "$OUT")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=unwind \
  "$ROOT/core/creative_selection/lib.rs" \
  -o "$OUT"
