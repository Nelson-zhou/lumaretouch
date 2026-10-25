#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# AUTHORED / UNRUN. Only execute in a separately authorized build environment.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
output=${1:-"$root/engine/src/lumaretouch_engine/bin/liblrt_portrait_crop.so"}
mkdir -p "$(dirname -- "$output")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=unwind \
  "$root/core/portrait_crop/lib.rs" -o "$output"
