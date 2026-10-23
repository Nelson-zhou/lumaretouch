#!/usr/bin/env bash
# Explicit distributor packaging only, never runtime compilation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_shoulder_shape.so}"
mkdir -p "$(dirname "$OUT")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=abort \
  "$ROOT/core/shoulder_shape/lib.rs" -o "$OUT"
