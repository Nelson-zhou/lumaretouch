#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Explicit packaging only. NOT run by Python import, UI start, preview or export.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_waist_shape.so}"
mkdir -p "$(dirname "$OUT")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=abort \
  "$ROOT/core/waist_shape/lib.rs" -o "$OUT"
