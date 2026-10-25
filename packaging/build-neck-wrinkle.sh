#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# AUTHORED / UNRUN. Build only after separate execution authorization.
# AGPL-3.0-only RapidRetouch derivative; no downloads/runtime compilation.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_neck_wrinkle.so"}
mkdir -p "$(dirname -- "$out")"
temporary=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
rustc --edition=2021 --crate-name lrt_neck_wrinkle --crate-type cdylib \
    -C opt-level=3 -C panic=unwind "$here/../core/neck_wrinkle/lib.rs" -o "$temporary"
chmod 0644 "$temporary"
mv -f -- "$temporary" "$out"
