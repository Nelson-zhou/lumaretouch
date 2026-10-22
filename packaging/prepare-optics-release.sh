#!/usr/bin/env bash
# Explicit release producer. Network steps are named; staging itself is offline.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
bundle=${LRT_OPTICS_BUNDLE:-$root/build/optics/bundle}
cache=${LRT_OPTICS_CACHE:-$root/build/optics/cache}
export LRT_OPTICS_APPLICATION_COMMIT=$(git -C "$root" rev-parse HEAD)
if [[ ${LRT_ALLOW_MISSING_OPTICS:-0} == 1 ]]; then
  echo 'Development optics opt-out is forbidden for the release producer.' >&2; exit 1
fi
if [[ -f "$bundle/BUNDLE.json" ]]; then
  python3 "$here/setup-optics.py" verify --bundle "$bundle"
  exit 0
fi
if [[ ${1:-} != --acquire || ${LRT_OPTICS_OFFLINE:-0} == 1 ]]; then
  echo 'No prepared optics bundle. Run prepare-optics-release.sh --acquire explicitly, or provide a verified same-commit LRT_OPTICS_BUNDLE. No network action performed.' >&2; exit 1
fi
for tool in git cmake pkg-config cc c++ readelf; do
  command -v "$tool" >/dev/null || { echo "Missing release tool $tool; Ubuntu prerequisites: build-essential cmake pkg-config libglib2.0-dev python3.12-venv binutils" >&2; exit 1; }
done
pkg-config --exists glib-2.0
py=${LRT_OPTICS_PYTHON:-python3.12}
"$py" -c 'import sys; assert sys.version_info[:2]==(3,12)'
mkdir -p "$cache"
venv="$cache/build-venv"
if [[ ! -x "$venv/bin/python" ]]; then "$py" -m venv "$venv"; fi
echo 'RELEASE ACQUISITION: install pinned build tools from official PyPI into the isolated build venv; fetch exact Lensfun and lensfunpy commits from official GitHub. No images/models are uploaded or downloaded.'
"$venv/bin/python" -m pip install --index-url https://pypi.org/simple --report "$cache/build-tool-report.json" -r "$here/requirements-optics-build.txt"
"$venv/bin/python" "$here/setup-optics.py" fetch --cache "$cache"
"$venv/bin/python" "$here/setup-optics.py" build --cache "$cache" --bundle "$bundle" --python "$venv/bin/python"
"$venv/bin/python" "$here/setup-optics.py" verify --bundle "$bundle"
