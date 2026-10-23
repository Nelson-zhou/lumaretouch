#!/bin/sh
# Authored, UNRUN. Build only in the authorized Qoder/release environment.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_creative_layers.so"}
mkdir -p "$(dirname -- "$out")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$here/../core/creative_layers/lib.rs" -o "$out"
