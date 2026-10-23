#!/bin/sh
# AUTHORED / UNRUN. Build only when execution is separately authorized.
# No downloaded crates, network, runtime compilation or substitute algorithm.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_red_eye.so"}
mkdir -p "$(dirname -- "$out")"
temporary=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
rustc --edition=2021 --crate-name lrt_red_eye --crate-type cdylib \
    -C opt-level=3 -C panic=unwind "$here/../core/red_eye/lib.rs" -o "$temporary"
chmod 0644 "$temporary"
mv -f -- "$temporary" "$out"
