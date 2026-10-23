#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Explicit packaging only. UNRUN during source authoring. Never runtime compile.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_lipstick.so}"
mkdir -p "$(dirname "$OUT")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=abort "$ROOT/core/lipstick/lib.rs" -o "$OUT"
