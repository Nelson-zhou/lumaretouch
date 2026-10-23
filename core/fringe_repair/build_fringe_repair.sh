#!/bin/sh
# AUTHORED UNRUN. For the separately authorized local build/QA environment only.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$root/engine/src/lumaretouch_engine/bin"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 \
  "$root/core/fringe_repair/lib.rs" \
  -o "$root/engine/src/lumaretouch_engine/bin/liblrt_fringe_repair.so"
