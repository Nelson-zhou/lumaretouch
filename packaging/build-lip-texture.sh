#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# AUTHORED / UNRUN. Build only after separate execution authorization.
# Original std-only Rust; no external downloads/crates or runtime compilation.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_lip_texture.so"}
mkdir -p "$(dirname -- "$out")"
temporary=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
rustc --edition=2021 --crate-name lrt_lip_texture --crate-type cdylib \
    -C opt-level=3 -C panic=unwind "$here/../core/lip_texture/lib.rs" -o "$temporary"
chmod 0644 "$temporary"
mv -f -- "$temporary" "$out"
