#!/bin/sh
# UNRUN: dedicated build entry for separately authorized local testing only.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$ROOT/engine/src/lumaretouch_engine/bin"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$ROOT/core/iris_makeup/lib.rs" -o "$ROOT/engine/src/lumaretouch_engine/bin/liblrt_iris_makeup.so"
