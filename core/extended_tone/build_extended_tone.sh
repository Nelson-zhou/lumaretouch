#!/bin/sh
# AUTHORED, NOT RUN. Invoke only in the authorized local test/build environment.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$root/engine/src/lumaretouch_engine/bin"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$root/core/extended_tone/extended_tone.rs" -o "$root/engine/src/lumaretouch_engine/bin/liblrt_extended_tone.so"
