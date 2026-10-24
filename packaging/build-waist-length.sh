#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Explicit distributor packaging only, never runtime compilation. Authored UNRUN.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_waist_length.so}"
mkdir -p "$(dirname "$OUT")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=abort \
  "$ROOT/core/waist_length/lib.rs" -o "$OUT"
