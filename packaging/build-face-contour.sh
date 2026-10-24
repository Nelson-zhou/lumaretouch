#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# AUTHORED / UNRUN. Explicit packaging only; never invoked at application runtime.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_face_contour.so}"
mkdir -p "$(dirname "$OUT")"
temporary=$(mktemp "${OUT}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=unwind \
  "$ROOT/core/face_contour/lib.rs" -o "$temporary"
chmod 0644 "$temporary"
mv -f -- "$temporary" "$OUT"
