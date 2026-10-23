#!/bin/sh
# AUTHORED UNRUN. Run only in the authorized local build environment.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$root/engine/src/lumaretouch_engine/bin"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$root/core/photo_detail/photo_detail.rs" -o "$root/engine/src/lumaretouch_engine/bin/liblrt_photo_detail.so"
