#!/usr/bin/env bash
# Repository-owned fixed-size classical estimator. AUTHORED / UNRUN here.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/../engine/src/lumaretouch_engine/bin/white-balance-auto"}
command -v rustc >/dev/null || { echo 'rustc is required for automatic white balance' >&2; exit 1; }
mkdir -p "$(dirname "$out")"
rustc --edition=2021 -O "$here/../core/white_balance/automatic_main.rs" -o "$out"
