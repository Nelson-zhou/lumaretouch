#!/usr/bin/env sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Explicit distributor packaging artifact only. AUTHORED / UNRUN.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
out=${1:-"$ROOT/engine/src/lumaretouch_engine/bin/liblrt_body_slim.so"}
mkdir -p "$(dirname -- "$out")"
temporary=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$ROOT/core/body_slim/lib.rs" -o "$temporary"
chmod 0644 "$temporary"
mv -f -- "$temporary" "$out"
