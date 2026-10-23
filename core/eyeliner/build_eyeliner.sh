#!/bin/sh
# Authored only, UNRUN. Invoke explicitly in authorized local validation.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$root/engine/src/lumaretouch_engine/bin"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$root/core/eyeliner/eyeliner.rs" -o "$root/engine/src/lumaretouch_engine/bin/liblrt_eyeliner.so"
