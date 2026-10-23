#!/bin/sh
set -eu
# Packaging-only entry point. Not executed during implementation review.
cd "$(dirname "$0")"
mkdir -p ../../engine/src/lumaretouch_engine/bin
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=abort lib.rs -o ../../engine/src/lumaretouch_engine/bin/liblrt_colour_editor.so
