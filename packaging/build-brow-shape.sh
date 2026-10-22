#!/usr/bin/env bash
# Explicit source packaging only. Never invoked at runtime.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_brow_shape.so}"
mkdir -p "$(dirname "$OUT")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=abort \
  "$ROOT/core/brow_shape/lib.rs" -o "$OUT"
