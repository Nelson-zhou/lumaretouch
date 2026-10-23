#!/usr/bin/env bash
# Source-authored build hook, UNRUN in integration task.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_eye_light.so}"
mkdir -p "$(dirname "$OUT")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$ROOT/core/eye_light/lib.rs" -o "$OUT"
