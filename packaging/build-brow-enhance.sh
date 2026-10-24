#!/bin/sh
# AUTHORED / UNRUN. Separate authorization required before any compilation.
# Original Rust with no external crates, downloads or runtime compilation.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_brow_enhance.so"}
mkdir -p "$(dirname -- "$out")"
temporary=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
rustc --edition=2021 --crate-name lrt_brow_enhance --crate-type cdylib \
    -C opt-level=3 -C panic=unwind "$here/../core/brow_enhance/lib.rs" -o "$temporary"
chmod 0644 "$temporary"
mv -f -- "$temporary" "$out"
