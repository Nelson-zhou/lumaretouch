#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Authored build recipe only; not executed or runtime-compiled.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/liblrt_hand_tone.so"}
mkdir -p "$(dirname -- "$out")"
rustc --edition=2021 --crate-name lrt_hand_tone --crate-type cdylib -C opt-level=3 -C panic=unwind "$here/../core/hand_tone/lib.rs" -o "$out"
