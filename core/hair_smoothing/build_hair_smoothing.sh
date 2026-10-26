#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# AUTHORED / UNRUN. Execute only in an explicitly authorized build environment.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
output=${1:-"$root/engine/src/lumaretouch_engine/bin/liblrt_hair_smoothing.so"}
mkdir -p "$(dirname -- "$output")"
temporary=$(mktemp "${output}.tmp.XXXXXXXX")
trap 'rm -f -- "$temporary"' EXIT HUP INT TERM
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=unwind \
  "$root/core/hair_smoothing/lib.rs" -o "$temporary"
# A failed/interrupted compile never replaces the previously installed core.
mv -f -- "$temporary" "$output"
trap - EXIT HUP INT TERM
