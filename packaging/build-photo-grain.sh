#!/usr/bin/env bash
# Build-time only, offline std-only. NOT run during source implementation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_photo_grain.so}"
mkdir -p "$(dirname "$OUT")"
rustc --edition=2021 --crate-type cdylib -O "$ROOT/core/photo_grain/lib.rs" -o "$OUT"
