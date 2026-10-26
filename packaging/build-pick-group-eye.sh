#!/bin/sh
# SOURCE ONLY / UNRUN. No crates, downloads or runtime compilation.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_pick_group_eye.so"}
mkdir -p "$(dirname -- "$out")"
temporary=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
rustc --edition=2021 --crate-name lrt_pick_group_eye --crate-type cdylib \
    -C opt-level=3 "$here/../core/pick_group_eye/lib.rs" -o "$temporary"
chmod 0644 "$temporary"
mv -f -- "$temporary" "$out"
