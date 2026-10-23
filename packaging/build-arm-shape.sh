#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Explicit packaging only. NOT run by Python import, UI start, preview or export.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/engine/src/lumaretouch_engine/bin"
mkdir -p "$DEST"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=abort \
  "$ROOT/core/arm_shape/lib.rs" -o "$DEST/liblrt_arm_shape.so"
