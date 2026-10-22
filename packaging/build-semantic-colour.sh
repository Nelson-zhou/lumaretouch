#!/usr/bin/env bash
# Build-time only. Dependency-free Rust; never compile or download at runtime.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_semantic_colour.so}"
mkdir -p "$(dirname "$OUT")"
rustc --edition=2021 --crate-type cdylib -O "$ROOT/core/semantic_colour/lib.rs" -o "$OUT"
