#!/bin/sh
# AUTHORED, UNRUN. Qoder/local QA owns build and tests under the execution gate.
# No runtime compilation or downloaded dependency is used by the application.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$root/engine/src/lumaretouch_engine/bin"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 \
  "$root/core/creative_layers/lib.rs" \
  -o "$root/engine/src/lumaretouch_engine/bin/liblrt_creative_layers.so"
