#!/usr/bin/env bash
# Build-time only. No dependency download and no runtime compilation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_reference_color.so}"
mkdir -p "$(dirname "$OUT")"
rustc --edition=2021 --crate-type cdylib -O "$ROOT/core/reference_color/lib.rs" -o "$OUT"
