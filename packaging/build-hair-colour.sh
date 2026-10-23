#!/usr/bin/env bash
# Explicit source packaging only; no runtime compilation or downloads.
# Keep unwinding enabled so the C ABI can return 99 for a caught Rust panic.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_hair_colour.so}"
mkdir -p "$(dirname "$OUT")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=unwind \
  "$ROOT/core/hair_colour/lib.rs" -o "$OUT"
