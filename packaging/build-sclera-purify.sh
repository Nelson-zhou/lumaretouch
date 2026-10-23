#!/bin/sh
# AUTHORED / UNRUN. Build only when execution is separately authorized.
# No external crates, downloads, runtime compilation or substitute algorithm.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_sclera_purify.so"}
mkdir -p "$(dirname -- "$out")"
temporary=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
rustc --edition=2021 --crate-name lrt_sclera_purify --crate-type cdylib \
    -C opt-level=3 -C panic=unwind "$here/../core/sclera_purify/lib.rs" -o "$temporary"
chmod 0644 "$temporary"
mv -f -- "$temporary" "$out"
