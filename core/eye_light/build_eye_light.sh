#!/bin/sh
# UNRUN dedicated build entry. Only authorized local tester should invoke.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$ROOT/engine/src/lumaretouch_engine/bin"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$ROOT/core/eye_light/lib.rs" -o "$ROOT/engine/src/lumaretouch_engine/bin/liblrt_eye_light.so"
