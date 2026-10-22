#!/usr/bin/env bash
# Normal packaging requires the real offline runtime/database bundle. Never fetch.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
stage=${1:?engine staging directory required}
bundle=${LRT_OPTICS_BUNDLE:-$here/../build/optics/bundle}
if [[ ! -f "$bundle/BUNDLE.json" ]]; then
  if [[ ${LRT_ALLOW_MISSING_OPTICS:-0} == 1 ]]; then
    printf '%s\n' 'DEVELOPMENT ONLY: Lensfun runtime/database not bundled; optical automatic profile correction will be unavailable.' > "$stage/runtime/OPTICS-NOT-BUNDLED.txt"
    echo 'WARNING: development opt-out, Lensfun not bundled' >&2
    exit 0
  fi
  echo 'Missing Lensfun runtime/database bundle. Release engineering must run setup-optics.py fetch then build, or provide LRT_OPTICS_BUNDLE. See docs/optics/INSTALL.md.' >&2
  exit 1
fi
LRT_OPTICS_APPLICATION_COMMIT=$(git -C "$here/.." rev-parse HEAD) python3 "$here/setup-optics.py" stage --bundle "$bundle" --destination "$stage/runtime/optics"
