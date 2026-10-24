#!/bin/sh
# AUTHORED / UNRUN. Build only after separate execution authorization.
# Original Rust, no external crates, downloads or runtime compilation.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_skin_colour.so"}
mkdir -p "$(dirname -- "$out")"
temporary=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
rustc --edition=2021 --crate-name lrt_skin_colour --crate-type cdylib \
    -C opt-level=3 -C panic=unwind "$here/../core/skin_colour/lib.rs" -o "$temporary"
chmod 0644 "$temporary"
mv -f -- "$temporary" "$out"
