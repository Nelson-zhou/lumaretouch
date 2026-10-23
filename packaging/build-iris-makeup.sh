#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# UNRUN: explicit authorized packaging only; never runtime compilation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/engine/src/lumaretouch_engine/bin/liblrt_iris_makeup.so}"
mkdir -p "$(dirname "$OUT")"
rustc --edition=2021 --crate-type cdylib -C opt-level=3 -C panic=abort "$ROOT/core/iris_makeup/lib.rs" -o "$OUT"
