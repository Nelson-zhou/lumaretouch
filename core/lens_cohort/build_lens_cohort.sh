#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# BUILD SCRIPT SOURCE ONLY. AUTHORED / UNRUN; execute only with authorization.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-"$here/../../engine/src/lumaretouch_engine/bin/liblrt_lens_cohort.so"}
mkdir -p "$(dirname -- "$out")"
temporary=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
rustc --edition=2021 --crate-name lrt_lens_cohort --crate-type cdylib \
    -C opt-level=3 -C panic=unwind "$here/lib.rs" -o "$temporary"
chmod 0644 "$temporary"
mv -f -- "$temporary" "$out"
