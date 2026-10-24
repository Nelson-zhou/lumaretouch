#!/usr/bin/env sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Explicit distributor packaging artifact only. AUTHORED / UNRUN.
# Do not execute under the static-only development gate.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$ROOT/engine/src/lumaretouch_engine/bin"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$ROOT/core/torso_length/lib.rs" -o "$ROOT/engine/src/lumaretouch_engine/bin/liblrt_torso_length.so"
