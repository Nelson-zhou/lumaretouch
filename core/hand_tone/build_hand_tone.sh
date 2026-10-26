#!/bin/sh
# AUTHORED / UNRUN. Explicit maintainer build only; never called by runtime.
set -eu
cd "$(dirname "$0")"
cargo build --release --locked
